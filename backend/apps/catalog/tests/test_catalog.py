from collections.abc import Callable
from datetime import timedelta
from io import StringIO
from typing import Any

import pytest
from django.contrib import admin
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import Client, RequestFactory, override_settings
from django.utils import timezone, translation

from apps.accounts.models import User
from apps.accounts.roles import CONTENIDO
from apps.audit.models import AuditLog
from apps.catalog.forms import PieceForm
from apps.catalog.models import Category, Collection, Material, Piece, PieceImage, Stone
from apps.catalog.services import (
    archive_piece,
    delete_piece,
    hide_pieces,
    publish_piece,
    save_piece,
    save_taxonomy,
    unhide,
)
from apps.catalog.validators import validate_attributes
from apps.core.exceptions import PublicationError
from apps.inventory.services import convert_reservation, reserve_piece

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "price,sale", [(0, None), (-1, None), (100, 0), (100, -1), (100, 100), (100, 101)]
)
def test_price_constraints(make_piece: Callable[..., Piece], price: int, sale: int | None) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        make_piece(published=False, price_cents=price, sale_price_cents=sale)


def test_unique_sku_and_primary(make_piece: Callable[..., Piece]) -> None:
    piece = make_piece()
    with pytest.raises(IntegrityError), transaction.atomic():
        make_piece(published=False, sku=piece.sku)
    with pytest.raises(IntegrityError), transaction.atomic():
        PieceImage.objects.create(
            piece=piece, original="other.webp", alt_es="Otra", position=1, is_primary=True
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        PieceImage.objects.create(piece=piece, original="other.webp", alt_es="Otra", position=0)


@pytest.mark.parametrize("model", [Category, Collection, Stone, Material, Piece])
def test_language_slug_constraints(model: Any) -> None:
    extra = {"sku": "A", "price_cents": 100} if model is Piece else {}
    model.objects.create(name_es="A", slug_es="a", slug_en="", **extra)
    if model is Piece:
        extra["sku"] = "B"
    model.objects.create(name_es="B", slug_es="b", slug_en="", **extra)
    with pytest.raises(IntegrityError), transaction.atomic():
        if model is Piece:
            extra["sku"] = "C"
        model.objects.create(name_es="C", slug_es="a", slug_en="c", **extra)
    model.objects.filter(slug_es="a").update(slug_en="unique")
    with pytest.raises(IntegrityError), transaction.atomic():
        model.objects.filter(slug_es="b").update(slug_en="unique")


@pytest.mark.parametrize(
    "attributes",
    [
        {"unknown": 1},
        {"carats": "one"},
        {"weight_g": True},
        {"metal": 18},
        [],
        {"dimensions_mm": []},
    ],
)
def test_attributes_rejected(attributes: object) -> None:
    with pytest.raises(ValidationError):
        validate_attributes(attributes)


def test_attributes_valid() -> None:
    validate_attributes(
        {
            "ring_size": "7",
            "length_mm": 12.5,
            "metal": "oro",
            "metal_purity": "18k",
            "carats": 1.2,
            "weight_g": 5,
            "dimensions_mm": "10x20",
        }
    )


def test_category_depth() -> None:
    parent = Category.objects.create(name_es="A", slug_es="a")
    child = Category.objects.create(name_es="B", slug_es="b", parent=parent)
    with pytest.raises(ValidationError):
        save_taxonomy(Category(name_es="C", slug_es="c", parent=child))
    parent.parent = child
    with pytest.raises(ValidationError):
        save_taxonomy(parent)


def test_publication_rules_audit_and_terminal_state(make_piece: Callable[..., Piece]) -> None:
    piece = make_piece(published=False, short_description_es="")
    with pytest.raises(PublicationError, match=r"descripción corta.*imagen"):
        publish_piece(piece, None)
    piece = make_piece(sale_price_cents=90_000)
    first_published = piece.published_at
    piece.price_cents = 120_000
    save_piece(piece, actor=None)
    event = AuditLog.objects.filter(action="catalog.piece_updated").last()
    assert event is not None
    assert event.diff["price_cents"] == [
        100_000,
        120_000,
    ]
    reservation = reserve_piece(
        piece.pk,
        kind="online",
        reference="order",
        expires_at=timezone.now() + timedelta(minutes=30),
    )
    convert_reservation(reservation.pk, reason="payment_approved")
    hide_pieces(Piece.objects.filter(pk=piece.pk), None)
    unhide(piece, None)
    piece.refresh_from_db()
    assert piece.sale_state == "sold"
    assert piece.published_at == first_published
    archive_piece(piece, None)
    assert set(AuditLog.objects.values_list("action", flat=True)) >= {
        "catalog.piece_published",
        "catalog.piece_hidden",
        "catalog.piece_archived",
        "catalog.piece_updated",
    }
    piece.refresh_from_db()
    piece.sale_state = "available"
    with pytest.raises(ValidationError):
        save_piece(piece, actor=None)
    with pytest.raises(ValidationError):
        delete_piece(piece)
    draft = make_piece(published=False)
    delete_piece(draft)
    assert not Piece.objects.filter(pk=draft.pk).exists()


def test_content_price_defence_and_form(make_piece: Callable[..., Piece]) -> None:
    user = User.objects.create_user(username="editor", email="editor@example.com", is_staff=True)
    user.groups.add(Group.objects.get(name=CONTENIDO))
    piece = make_piece()
    request = RequestFactory().get("/")
    request.user = user
    piece_admin = admin.site._registry[Piece]
    assert {"price_cents", "sale_price_cents"} <= set(
        piece_admin.get_readonly_fields(request, piece)
    )
    piece.name = "Editada"
    save_piece(piece, actor=user)
    piece.price_cents += 100
    with pytest.raises(PermissionDenied):
        save_piece(piece, actor=user)
    assert "sale_state" not in PieceForm().fields
    form = PieceForm(instance=piece)
    field = form.fields["price_cents"]
    assert field.clean("2500") == 250_000
    assert field.prepare_value(250_000) == 2500
    assert piece_admin.get_prepopulated_fields(request, piece) == {}


def test_missing_translations(make_piece: Callable[..., Piece]) -> None:
    make_piece(published=False, name_en="", slug_en="", short_description_en="")
    piece = make_piece(name_en="", slug_en="", short_description_en="")
    with pytest.raises(SystemExit) as exc:
        call_command("missing_translations", stdout=StringIO())
    assert exc.value.code == 1
    Piece.objects.filter(pk=piece.pk).update(
        name_en="Complete", slug_en="complete", short_description_en="Complete"
    )
    call_command("missing_translations", stdout=StringIO())


def test_seed_debug_guard() -> None:
    with pytest.raises(CommandError):
        call_command("seed_catalog")


def test_seed_idempotent() -> None:
    with override_settings(DEBUG=True):
        call_command("seed_catalog", stdout=StringIO())
        ids = list(Piece.objects.values_list("pk", flat=True))
        call_command("seed_catalog", stdout=StringIO())
    assert Piece.objects.count() == 12
    assert list(Piece.objects.values_list("pk", flat=True)) == ids
    assert PieceImage.objects.filter(processing_status="ready").count() == 12
    assert set(Piece.objects.values_list("sale_state", flat=True)) == {
        "available",
        "sold",
        "preorder",
    }
    call_command("missing_translations", stdout=StringIO())


@pytest.mark.postgres
def test_unaccent_trigram_search(client: Client, make_piece: Callable[..., Piece]) -> None:
    piece = make_piece(name_es="Órbita ZAFÍRO")
    with translation.override("es"):
        response = client.get("/api/v1/catalog/pieces", {"q": "orbita"})
    assert response.status_code == 200
    assert [item["sku"] for item in response.json()["results"]] == [piece.sku]


def test_admin_renders_translations_and_pesos(
    client: Client, make_piece: Callable[..., Piece]
) -> None:
    user = User.objects.create_user(username="ops", email="ops@example.com", is_staff=True)
    user.groups.add(Group.objects.get(name="Operaciones"))
    piece = make_piece()
    client.force_login(user)
    url = f"/dashboard/catalog/piece/{piece.pk}/change/"
    response = client.get(url)
    assert response.status_code == 200
    html = response.content.decode()
    assert 'name="name_es"' in html and 'name="name_en"' in html
    assert 'name="price_cents" value="1000"' in html
    assert "tabbed_translation_fields.js" in html
    assert 'name="sale_state"' not in html
    assert 'name="status"' not in html


def test_api_related_excludes_hidden(client: Client, make_piece: Callable[..., Piece]) -> None:
    piece = make_piece()
    hidden = make_piece()
    fallback = make_piece()
    hide_pieces(Piece.objects.filter(pk=hidden.pk), None)
    response = client.get(f"/api/v1/catalog/pieces/{piece.slug}")
    assert response.status_code == 200
    assert [row["sku"] for row in response.json()["related"]] == [fallback.sku]
    piece.related.add(hidden)
    response = client.get(f"/api/v1/catalog/pieces/{piece.slug}")
    assert [row["sku"] for row in response.json()["related"]] == [fallback.sku]


def test_related_self_constraint(make_piece: Callable[..., Piece]) -> None:
    piece = make_piece(published=False)
    with pytest.raises(IntegrityError), transaction.atomic():
        piece.related.add(piece)
