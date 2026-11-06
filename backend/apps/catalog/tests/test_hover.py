from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from django.contrib import admin
from django.core.files.uploadedfile import SimpleUploadedFile, UploadedFile
from django.db import IntegrityError, transaction
from django.forms import inlineformset_factory
from django.test import Client
from django.utils.datastructures import MultiValueDict

from apps.catalog.admin import PieceImageInline
from apps.catalog.api.serializers import ImageSerializer, PieceListSerializer
from apps.catalog.forms import PieceImageForm, PieceImageFormSet
from apps.catalog.models import Piece, PieceImage
from apps.catalog.selectors import published_pieces
from apps.catalog.services import delete_piece_image, save_piece_image

from .conftest import image_file

pytestmark = pytest.mark.django_db


def hover(piece: Piece) -> PieceImage:
    image = PieceImage(
        piece=piece,
        original="hover.webp",
        alt_es="Alternativa",
        position=1,
        is_hover=True,
        processing_status="ready",
    )
    save_piece_image(image)
    return image


def test_constraints(make_piece: Callable[..., Piece]) -> None:
    piece = make_piece()
    image = hover(piece)
    with pytest.raises(IntegrityError), transaction.atomic():
        PieceImage.objects.create(piece=piece, original="other.webp", position=2, is_hover=True)
    with pytest.raises(IntegrityError), transaction.atomic():
        PieceImage.objects.filter(pk=image.pk).update(is_primary=True)


@pytest.mark.parametrize("status", ["pending", "failed", "ready"])
def test_payload_and_deletion(
    make_piece: Callable[..., Piece], client: Client, status: str
) -> None:
    piece = make_piece()
    assert PieceListSerializer(piece).data["hover_image"] is None
    unmarked = PieceImage(
        piece=piece,
        original="gallery.webp",
        position=2,
        alt_es="Galería",
        processing_status="ready",
    )
    save_piece_image(unmarked)
    assert PieceListSerializer(piece).data["hover_image"] is None
    image = hover(piece)
    image.processing_status = status
    image.save(update_fields=["processing_status"])
    expected = dict(ImageSerializer(image).data) if status == "ready" else None
    assert PieceListSerializer(piece).data["hover_image"] == expected
    listing = client.get("/api/v1/catalog/pieces", {"q": piece.name_es}).json()
    assert listing["results"][0]["hover_image"] == expected
    assert client.get(f"/api/v1/catalog/pieces/{piece.slug}").json()["hover_image"] == expected
    delete_piece_image(image)
    data = client.get("/api/v1/catalog/pieces").json()["results"][0]
    assert data["hover_image"] is None
    assert data["image"] is not None


@pytest.mark.parametrize("both", [False, True])
def test_inline_validation(make_piece: Callable[..., Piece], both: bool) -> None:
    piece = make_piece(published=False)
    factory = inlineformset_factory(
        Piece,
        PieceImage,
        form=PieceImageForm,
        formset=PieceImageFormSet,
        fields=("original", "alt_es", "position", "is_primary", "is_hover"),
        extra=2,
    )
    data: dict[str, Any] = {"images-TOTAL_FORMS": "2", "images-INITIAL_FORMS": "0"}
    for index in range(2):
        data.update(
            {
                f"images-{index}-alt_es": "Alternativa",
                f"images-{index}-position": index,
                f"images-{index}-is_hover": "on",
            }
        )
    if both:
        data["images-0-is_primary"] = "on"
    files: MultiValueDict[str, UploadedFile[Any]] = MultiValueDict(
        {
            f"images-{i}-original": [
                SimpleUploadedFile("test.png", image_file().read(), "image/png")
            ]
            for i in range(2)
        }
    )
    formset = factory(data, files=files, instance=piece)
    assert not formset.is_valid()
    errors = str(formset.errors if both else formset.non_form_errors())
    assert ("no puede ser principal" if both else "solo una imagen al pasar") in errors
    data["images-0-DELETE"] = "on"
    # The remaining photo must now be the primary (and cannot also be hover).
    data["images-1-is_primary"] = "on"
    data.pop("images-1-is_hover")
    files = MultiValueDict(
        {
            f"images-{i}-original": [
                SimpleUploadedFile("test.png", image_file().read(), "image/png")
            ]
            for i in range(2)
        }
    )
    assert factory(data, files=files, instance=piece).is_valid()


def test_queries_do_not_grow(
    make_piece: Callable[..., Piece], django_assert_num_queries: Any
) -> None:
    for count in (1, 5):
        while Piece.objects.count() < count:
            hover(make_piece())
        with django_assert_num_queries(5):
            rows = PieceListSerializer(published_pieces(), many=True).data
            assert len(rows) == count
            assert all(row["hover_image"] for row in rows)


def test_hover_replacement_and_preview(
    make_piece: Callable[..., Piece], django_capture_on_commit_callbacks: Any
) -> None:
    image = hover(make_piece())
    image.original = image_file()
    with django_capture_on_commit_callbacks(execute=True):
        save_piece_image(image)
    image.refresh_from_db()
    assert image.is_hover and image.processing_status == "ready"
    inline = PieceImageInline(Piece, admin.site)
    assert image.renditions["webp"]["480"] in inline.preview(image)
    image.renditions = {}
    assert image.original.url in inline.preview(image)
    assert inline.preview(PieceImage()) == "—"


def test_cart_hover_contract(make_piece: Callable[..., Piece], client: Client) -> None:
    piece = make_piece()
    image = hover(piece)
    response = client.post(
        "/api/v1/cart/items",
        {"sku": piece.sku},
        content_type="application/json",
        REMOTE_ADDR="192.0.2.45",
    )
    assert response.status_code == 201
    assert response.json()["items"][0]["hover_image"] == dict(ImageSerializer(image).data)
    delete_piece_image(image)
    assert (
        client.get("/api/v1/cart", REMOTE_ADDR="192.0.2.45").json()["items"][0]["hover_image"]
        is None
    )


def test_related_hover_contract(make_piece: Callable[..., Piece], client: Client) -> None:
    piece = make_piece()
    related = make_piece()
    image = hover(related)
    data = client.get(f"/api/v1/catalog/pieces/{piece.slug}").json()
    assert data["related"][0]["hover_image"] == dict(ImageSerializer(image).data)


def test_home_rail_hover_is_live(make_piece: Callable[..., Piece]) -> None:
    from apps.catalog.models import Collection, CollectionPiece
    from apps.catalog.services import save_collection_piece, save_taxonomy
    from apps.cms.selectors import resolve_live

    piece = make_piece()
    image = hover(piece)
    collection = Collection(name_es="Selección", slug_es="seleccion")
    save_taxonomy(collection)
    save_collection_piece(CollectionPiece(collection=collection, piece=piece))

    def rail() -> list[dict[str, Any]]:
        return resolve_live([{"kind": "collection_rail", "collection_id": collection.pk}], "es")

    assert rail()[0]["pieces"][0]["hover_image"] == dict(ImageSerializer(image).data)
    delete_piece_image(image)
    assert rail()[0]["pieces"][0]["hover_image"] is None
