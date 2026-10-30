from collections.abc import Callable
from typing import Any
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image

from apps.catalog.images import MAX_BYTES, validated_image
from apps.catalog.models import Category, Piece, PieceImage
from apps.catalog.services import save_piece_image, save_taxonomy
from apps.catalog.tasks import process_piece_image

from .conftest import image_file

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_pipeline_formats_and_no_metadata(
    fmt: str, make_piece: Callable[..., Piece], django_capture_on_commit_callbacks: Any
) -> None:
    piece = make_piece(published=False)
    exif = Image.Exif()
    exif[0x010F] = "Private camera"
    exif[0x8825] = {1: "N", 2: (4, 35, 0), 3: "W", 4: (74, 4, 0)}
    upload = image_file(fmt, (1000, 1250), exif=exif)
    photo = PieceImage(piece=piece, original=upload, alt_es="Una pieza", is_primary=True)
    with django_capture_on_commit_callbacks(execute=True):
        save_piece_image(photo)
    photo.refresh_from_db()
    assert photo.processing_status == "ready"
    assert (photo.width, photo.height) == (1000, 1250)
    assert set(photo.renditions["webp"]) == {"480", "960"}
    for path in [photo.original.name, *photo.renditions["webp"].values()]:
        with default_storage.open(path, "rb") as source, Image.open(source) as result:
            assert result.format == "WEBP"
            assert not result.getexif()
            assert "exif" not in result.info
    previous = list(photo.renditions["webp"].values())
    with django_capture_on_commit_callbacks(execute=True):
        process_piece_image(photo.pk)
    photo.refresh_from_db()
    assert photo.processing_status == "ready"
    assert set(photo.renditions["webp"]) == {"480", "960"}
    assert all(not default_storage.exists(path) for path in previous)


def test_exif_orientation(
    make_piece: Callable[..., Piece], django_capture_on_commit_callbacks: Any
) -> None:
    exif = Image.Exif()
    exif[0x0112] = 6
    piece = make_piece(published=False)
    photo = PieceImage(
        piece=piece, original=image_file("JPEG", (1000, 600), exif=exif), alt_es="Vertical"
    )
    with django_capture_on_commit_callbacks(execute=True):
        save_piece_image(photo)
    photo.refresh_from_db()
    assert (photo.width, photo.height) == (600, 1000)
    assert set(photo.renditions["webp"]) == {"480", "600"}  # source width kept


def test_tiny_image_and_failed_task(
    make_piece: Callable[..., Piece], django_capture_on_commit_callbacks: Any
) -> None:
    photo = PieceImage(
        piece=make_piece(published=False), original=image_file(size=(120, 150)), alt_es="Pequeña"
    )
    with django_capture_on_commit_callbacks(execute=True):
        save_piece_image(photo)
    photo.refresh_from_db()
    assert set(photo.renditions["webp"]) == {"120"}
    with patch("apps.catalog.tasks.validated_image", side_effect=ValueError("secret stack trace")):
        process_piece_image(photo.pk)
    photo.refresh_from_db()
    assert photo.processing_status == "failed"
    assert "secret" not in photo.error
    process_piece_image(photo.pk)
    photo.refresh_from_db()
    assert photo.processing_status == "ready"


@pytest.mark.parametrize(
    "data", [b'<svg xmlns="http://www.w3.org/2000/svg"/>', b"GIF89a", b"not an image"]
)
def test_invalid_images(data: bytes) -> None:
    with pytest.raises(ValidationError):
        validated_image(ContentFile(data, name="looks-like.jpeg"))


def test_gif_truncated_and_size_limits() -> None:
    for upload in [
        image_file("GIF"),
        ContentFile(image_file("JPEG").read()[:-20]),
        ContentFile(b"x" * (MAX_BYTES + 1)),
    ]:
        with pytest.raises(ValidationError):
            validated_image(upload)
    with (
        patch("apps.catalog.images.MAX_PIXELS", 100),
        pytest.raises(ValidationError, match="40 megapíxeles"),
    ):
        validated_image(image_file(size=(20, 20)))


def test_covers_are_validated_and_encoded() -> None:
    obj = Category(
        name_es="Portada", slug_es="portada", cover_image=image_file("JPEG", (1600, 900))
    )
    save_taxonomy(obj)
    with obj.cover_image.open("rb") as source, Image.open(source) as image:
        assert image.format == "WEBP"
        assert not image.getexif()
    assert (image.width, image.height) == (1600, 900)


@pytest.mark.parametrize("size", [(100, 100), (1920, 1081), (900, 1600)])
def test_covers_are_center_cropped_to_16_9(size: tuple[int, int]) -> None:
    obj = Category(name_es="Recorte", slug_es="recorte", cover_image=image_file("JPEG", size))
    save_taxonomy(obj)
    with obj.cover_image.open("rb") as source, Image.open(source) as image:
        assert image.width * 9 == image.height * 16


@pytest.mark.parametrize("fmt", ["JPEG", "PNG"])
def test_trailing_bytes_are_accepted_but_never_stored(fmt: str) -> None:
    # Phone JPEGs often carry extra data after the end marker; a polyglot does the same.
    payload = b"<script>alert(1)</script>"
    upload = ContentFile(image_file(fmt).read() + payload, name=f"phone.{fmt.lower()}")
    obj = Category(name_es="Telefono", slug_es="telefono", cover_image=upload)
    save_taxonomy(obj)
    with obj.cover_image.open("rb") as stored:
        assert payload not in stored.read()
