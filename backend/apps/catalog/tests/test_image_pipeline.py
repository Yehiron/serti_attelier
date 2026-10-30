from __future__ import annotations

from collections.abc import Callable
from io import StringIO
from typing import Any
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile, UploadedFile
from django.core.management import call_command
from django.db import transaction
from django.test import Client
from django.utils.datastructures import MultiValueDict
from django.utils.translation import override
from drf_spectacular.generators import SchemaGenerator
from PIL import Image

from apps.catalog.api.serializers import TaxonSerializer
from apps.catalog.forms import ValidatedImageForm
from apps.catalog.images import HEIF_AVAILABLE, MAX_BYTES, validated_image
from apps.catalog.models import Category, Collection, Material, Piece, PieceImage, Stone
from apps.catalog.services import rebuild_image, save_piece_image, save_taxonomy
from apps.cms.forms import ContentForm
from apps.cms.models import HomePublication, HomeSection, PersonalizationService
from apps.cms.selectors import resolve_live
from apps.cms.services import save_personalization, save_section

from .conftest import image_file

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("fmt", ["AVIF", "HEIF"])
def test_phone_formats(fmt: str) -> None:
    if fmt == "HEIF" and not HEIF_AVAILABLE:
        pytest.skip("pillow-heif is not installed; HEIC/HEIF decoder unavailable")
    exif = Image.Exif()
    exif[0x0112] = 6
    # Encoded EXIF bytes, as phones write them (pillow-heif ignores an Exif object).
    image = validated_image(image_file(fmt, (80, 40), exif=exif.tobytes()))
    assert image.size == (40, 80)
    assert not image.info
    assert not image.getexif()


def test_formats_message_and_limit() -> None:
    assert MAX_BYTES == 25 * 1024 * 1024
    with pytest.raises(ValidationError, match=r"Usa una imagen JPEG, PNG, WebP, AVIF o HEIC"):
        validated_image(image_file("GIF"))
    with patch("apps.catalog.images.MAX_BYTES", 50), pytest.raises(ValidationError, match="25 MB"):
        validated_image(image_file())


@pytest.mark.parametrize("fmt", ["AVIF", "HEIF"])
def test_admin_forms_accept_phone_formats(fmt: str) -> None:
    if fmt == "HEIF" and not HEIF_AVAILABLE:
        pytest.skip("pillow-heif is not installed; HEIC/HEIF admin upload unavailable")

    class CoverForm(ValidatedImageForm):
        class Meta:
            model = Category
            fields = ("name", "cover_image")

    class SectionForm(ContentForm):
        class Meta:
            model = HomeSection
            fields = ("kind", "image", "image_alt_es", "image_alt_en")

    def files(field: str) -> MultiValueDict[str, UploadedFile[Any]]:
        return MultiValueDict(
            {field: [SimpleUploadedFile(f"phone.{fmt.lower()}", image_file(fmt).read())]}
        )

    assert CoverForm({"name": "Phone"}, files("cover_image")).is_valid()
    form = SectionForm(
        {"kind": "hero", "image_alt_es": "Foto", "image_alt_en": "Photo"},
        files("image"),
    )
    assert form.is_valid(), form.errors


@pytest.mark.parametrize("model", [Category, Collection, Stone])
def test_cover_contract_and_cap(model: Any) -> None:
    obj = model(
        name_es="Piedra",
        name_en="Stone",
        slug_es="piedra",
        cover_image=image_file(size=(3200, 1800)),
    )
    save_taxonomy(obj)
    assert (obj.cover_width, obj.cover_height) == (2400, 1350)
    with obj.cover_image.open("rb") as source, Image.open(source) as master:
        assert master.size == (2400, 1350)
    with override("en"):
        data = TaxonSerializer(obj).data
    cover = data["cover"]
    assert set(cover) == {"src", "srcset", "width", "height", "alt"}
    assert cover["alt"] == "Stone"
    assert data["cover_image"] == cover["src"]
    assert cover["src"] == default_storage.url(obj.cover_renditions["webp"]["1600"])
    assert all(f"{width}w" in cover["srcset"] for width in (480, 960, 1600, 2400))
    if model is Stone:
        panel = resolve_live([{"kind": "stone_panels"}], "en")[0]
        assert panel["stones"][0]["image"] == cover
    assert TaxonSerializer(Material(name_es="Oro")).data["cover"] is None


@pytest.mark.parametrize("model", [HomeSection, PersonalizationService])
def test_cms_cap_replacement_and_clear(model: Any, django_capture_on_commit_callbacks: Any) -> None:
    kwargs = {"kind": "hero"} if model is HomeSection else {"title_es": "Servicio"}
    save = save_section if model is HomeSection else save_personalization
    obj = model(
        **kwargs, image=image_file(size=(3000, 3000)), image_alt_es="Foto", image_alt_en="Photo"
    )
    save(obj)
    assert max(obj.width, obj.height) == 2400
    old = {obj.image.name, *obj.renditions["webp"].values()}
    obj.image = image_file(size=(600, 600))
    with django_capture_on_commit_callbacks(execute=True):
        save(obj)
        assert all(default_storage.exists(path) for path in old)
    assert all(not default_storage.exists(path) for path in old)
    old = {obj.image.name, *obj.renditions["webp"].values()}
    obj.image = ""
    with django_capture_on_commit_callbacks(execute=True):
        save(obj)
    assert all(not default_storage.exists(path) for path in old)
    assert obj.renditions == {}


def test_cover_cleanup_rollback_shared_and_clear(django_capture_on_commit_callbacks: Any) -> None:
    obj = Category(name_es="Foto", slug_es="foto", cover_image=image_file())
    save_taxonomy(obj)
    old = {obj.cover_image.name, *obj.cover_renditions["webp"].values()}
    shared = Stone.objects.create(
        name_es="Compartida",
        cover_image=obj.cover_image.name,
        cover_renditions=obj.cover_renditions,
    )
    obj.cover_image = image_file(size=(800, 800))
    with django_capture_on_commit_callbacks(execute=True):
        save_taxonomy(obj)
    assert all(default_storage.exists(path) for path in old)
    with django_capture_on_commit_callbacks(execute=True):
        shared.delete()
    assert all(not default_storage.exists(path) for path in old)
    current = {obj.cover_image.name, *obj.cover_renditions["webp"].values()}
    pk = obj.pk
    with (
        django_capture_on_commit_callbacks(execute=True),
        pytest.raises(ValueError),
        transaction.atomic(),
    ):
        obj.delete()
        raise ValueError("rollback")
    obj.pk = pk
    assert all(default_storage.exists(path) for path in current)
    obj.refresh_from_db()
    obj.cover_image = ""
    with django_capture_on_commit_callbacks(execute=True):
        save_taxonomy(obj)
    assert all(not default_storage.exists(path) for path in current)


@pytest.mark.parametrize("cascade", [False, True])
def test_piece_deletion_and_replacement(
    make_piece: Callable[..., Piece],
    django_capture_on_commit_callbacks: Any,
    cascade: bool,
) -> None:
    piece = make_piece(published=False)
    photo = PieceImage(piece=piece, original=image_file(size=(3000, 1500)), alt_es="Foto")
    with django_capture_on_commit_callbacks(execute=True):
        save_piece_image(photo)
    photo.refresh_from_db()
    assert (photo.width, photo.height) == (2400, 1200)
    old = {photo.original.name, *photo.renditions["webp"].values()}
    photo.original = image_file(size=(700, 900))
    with django_capture_on_commit_callbacks(execute=True):
        save_piece_image(photo)
    assert all(not default_storage.exists(path) for path in old)
    photo.refresh_from_db()
    old = {photo.original.name, *photo.renditions["webp"].values()}
    with django_capture_on_commit_callbacks(execute=True):
        (piece if cascade else photo).delete()
        assert all(default_storage.exists(path) for path in old)
    assert all(not default_storage.exists(path) for path in old)


def test_publication_preserves_files(django_capture_on_commit_callbacks: Any) -> None:
    obj = HomeSection(kind="hero", image=image_file(), image_alt_es="Foto", image_alt_en="Photo")
    save_section(obj)
    paths = {obj.image.name, *obj.renditions["webp"].values()}
    HomePublication.objects.create(
        snapshot={"es": [{"srcset": ", ".join(f"{default_storage.url(p)} 960w" for p in paths)}]},
        draft_snapshot=[{"image": obj.image.name, "renditions": obj.renditions}],
    )
    obj.image = image_file(size=(500, 500))
    with django_capture_on_commit_callbacks(execute=True):
        save_section(obj)
    assert all(default_storage.exists(path) for path in paths)


def test_backfill_dry_run_idempotent_and_errors(make_piece: Callable[..., Piece]) -> None:
    cover = Category.objects.create(
        name_es="Legacy",
        slug_es="legacy",
        cover_image=image_file(size=(3200, 1800)),
    )
    photo = PieceImage.objects.create(
        piece=make_piece(published=False),
        original=image_file(size=(2800, 1400)),
        alt_es="Foto",
    )
    section = HomeSection.objects.create(kind="hero", image=image_file(size=(2800, 1600)))
    service = PersonalizationService.objects.create(image=image_file(size=(2800, 3000)))
    original = cover.cover_image.name
    out = StringIO()
    call_command("rebuild_images", dry_run=True, stdout=out)
    assert "procesadas: 4" in out.getvalue()
    cover.refresh_from_db()
    assert cover.cover_image.name == original
    assert not cover.cover_renditions
    out = StringIO()
    call_command("rebuild_images", stdout=out)
    assert "procesadas: 4" in out.getvalue()
    for obj in (cover, photo, section, service):
        obj.refresh_from_db()
        assert not rebuild_image(obj, dry_run=False)
    cover.cover_image = "missing.webp"
    cover.cover_renditions = {}
    cover.save()
    out, err = StringIO(), StringIO()
    call_command("rebuild_images", stdout=out, stderr=err)
    assert "errores: 1" in out.getvalue()
    assert "Error al procesar" in err.getvalue()


def test_empty_backfill() -> None:
    out = StringIO()
    call_command("rebuild_images", stdout=out)
    assert out.getvalue() == "procesadas: 0 / omitidas: 0 / errores: 0\n"


def test_taxonomy_http_and_schema_contract(client: Client) -> None:
    obj = Category(name_es="Foto", name_en="Photo", slug_es="foto", cover_image=image_file())
    save_taxonomy(obj)
    response = client.get("/api/v1/catalog/taxonomy", {"locale": "en"})
    assert response.status_code == 200
    category = next(row for row in response.json()["categories"] if row["slug"] == "foto")
    assert category["cover"]["alt"] == "Photo"
    assert category["cover_image"] == category["cover"]["src"]
    assert category["cover"]["srcset"]
    schema = SchemaGenerator().get_schema(request=None, public=True)  # type: ignore[no-untyped-call]
    assert schema is not None
    properties = schema["components"]["schemas"]["Taxon"]["properties"]
    assert properties["cover"]["nullable"]
    cover = schema["components"]["schemas"]["Cover"]["properties"]
    assert set(cover) == {"src", "srcset", "width", "height", "alt"}


def test_bomb_guard_and_partial_rendition_failure() -> None:
    from apps.catalog.images import build_renditions

    with patch.object(Image, "MAX_IMAGE_PIXELS", 100), pytest.raises(ValidationError):
        validated_image(image_file(size=(15, 10)))
    saved: list[str] = []
    real_save = default_storage.save

    def save_once(name: str, content: Any) -> str:
        if saved:
            raise OSError("storage unavailable")
        path = real_save(name, content)
        saved.append(path)
        return path

    with (
        patch.object(default_storage, "save", side_effect=save_once),
        pytest.raises(OSError),
    ):
        build_renditions(Image.new("RGB", (1000, 600)), "test/renditions")
    assert saved and not default_storage.exists(saved[0])


def test_backfill_repairs_incomplete_renditions() -> None:
    obj = Stone(name_es="Foto", cover_image=image_file())
    save_taxonomy(obj)
    path = obj.cover_renditions["webp"]["480"]
    default_storage.delete(path)
    assert rebuild_image(obj, dry_run=True)
    assert rebuild_image(obj, dry_run=False)
    obj.refresh_from_db()
    assert all(default_storage.exists(path) for path in obj.cover_renditions["webp"].values())
    assert not rebuild_image(obj, dry_run=False)


@pytest.mark.parametrize(
    "width,expected",
    [
        (750, ["480", "750"]),  # between standard sizes: keep the source width
        (1000, ["480", "960"]),  # within 10 % of 960: no near-duplicate
        (1921, ["480", "960", "1600", "1921"]),
        (300, ["300"]),  # smaller than every standard size
        (2400, ["480", "960", "1600", "2400"]),
    ],
)
def test_renditions_keep_the_source_width_between_standard_sizes(
    width: int, expected: list[str]
) -> None:
    from apps.catalog.images import build_renditions

    paths = build_renditions(Image.new("RGB", (width, 400)), "test/widths")
    assert sorted(paths, key=int) == expected
