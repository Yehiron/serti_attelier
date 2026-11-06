"""Auditoría transaccional desde los servicios y las rutas reales del administrador."""

from unittest.mock import patch

import pytest
from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import RequestFactory
from django.urls import reverse

from apps.accounts.roles import CONTENIDO, PROPIETARIO
from apps.audit.models import AuditLog
from apps.catalog import services
from apps.catalog.models import Category, Collection, CollectionPiece, Material, Piece, Stone
from apps.catalog.tests.conftest import image_file
from apps.catalog.tests.test_photo_management import photos_for
from apps.catalog.tests.test_stage3 import change_data
from apps.core.tests.test_dashboard_client import staff

pytestmark = pytest.mark.django_db


def request_for(user):
    request = RequestFactory().post(
        "/dashboard/", HTTP_USER_AGENT="Prueba de catálogo", REMOTE_ADDR="127.0.0.8"
    )
    request.user = user
    return request


def assert_context(log, user, obj):
    assert log.actor == user and log.object_id == str(obj.pk)
    assert log.content_type == ContentType.objects.get_for_model(obj)
    assert log.ip == "127.0.0.8" and log.user_agent == "Prueba de catálogo"


def test_relations_names_history_and_noop(make_piece):
    browser, user = staff(PROPIETARIO)
    piece, related = make_piece(published=False), make_piece(published=False)
    emerald = Stone.objects.create(name_es="Esmeralda", slug_es="esmeralda")
    diamond = Stone.objects.create(name_es="Diamante", slug_es="diamante")
    gold = Material.objects.create(name_es="Oro", slug_es="oro")
    piece.stones.add(emerald)
    values = {"stones": [emerald, diamond], "materials": [gold], "related": [related]}
    request = request_for(user)
    services.save_piece_relations(piece, values, actor=user, request=request)
    log = AuditLog.objects.get(action="catalog.relations_updated")
    assert_context(log, user, piece)
    assert log.diff == {
        "Piedras": [["Esmeralda"], ["Diamante", "Esmeralda"]],
        "Materiales": [[], ["Oro"]],
        "Piezas relacionadas": [[], [related.name_es]],
    }
    services.save_piece_relations(piece, values, actor=user, request=request)
    assert AuditLog.objects.filter(action=log.action).count() == 1
    history = browser.get(reverse("admin:catalog_piece_history", args=[piece.pk]))
    assert history.status_code == 200
    html = history.content.decode()
    assert "Historial del catálogo" in html and "Piedras: Esmeralda → Diamante, Esmeralda" in html
    assert "Prueba de catálogo" not in html and "127.0.0.8" not in html
    with pytest.raises(ValidationError):
        services.save_piece_relations(
            piece, {"materials": [], "related": [piece]}, actor=user, request=request
        )
    assert list(piece.materials.all()) == [gold]
    assert AuditLog.objects.filter(action=log.action).count() == 1


def test_real_piece_post_photos_relations_and_collections(make_piece):
    browser, user = staff(PROPIETARIO)
    piece = make_piece(published=False)
    photos_for(piece, 2)
    stone = Stone.objects.create(name_es="Esmeralda", slug_es="esmeralda")
    collection = Collection.objects.create(name_es="Aurora", slug_es="aurora")
    url, data = change_data(browser, piece)
    data |= {
        "stones": [stone.pk],
        "images-0-alt_es": "Anillo de esmeralda",
        "images-0-alt_en": "Emerald ring",
        "collectionpiece_set-TOTAL_FORMS": "1",
        "collectionpiece_set-INITIAL_FORMS": "0",
        "collectionpiece_set-0-collection": str(collection.pk),
        "collectionpiece_set-0-position": "0",
    }
    response = browser.post(
        url, data, HTTP_USER_AGENT="Prueba de catálogo", REMOTE_ADDR="127.0.0.8"
    )
    assert response.status_code == 302, response.context and response.context["errors"]
    logs = AuditLog.objects.filter(action="catalog.photos_updated")
    assert logs.count() == 1
    assert_context(logs.get(), user, piece)
    assert any(pair == ["Foto 0", "Anillo de esmeralda"] for pair in logs.get().diff.values())
    assert AuditLog.objects.get(action="catalog.relations_updated").diff["Piedras"] == [
        [],
        ["Esmeralda"],
    ]
    assert AuditLog.objects.get(action="catalog.collections_updated").diff == {
        "Colecciones": [[], ["Aurora"]]
    }
    history = browser.get(reverse("admin:catalog_piece_history", args=[piece.pk])).content.decode()
    assert "Anillo de esmeralda" in history and "Colecciones: Sin valor → Aurora" in history
    url, data = change_data(browser, piece)
    assert browser.post(url, data).status_code == 302
    assert logs.count() == 1


def test_collection_edit_delete_and_rollback(make_piece):
    _, user = staff(PROPIETARIO)
    request = request_for(user)
    piece = make_piece(published=False)
    first = Collection.objects.create(name_es="Aurora", slug_es="aurora")
    second = Collection.objects.create(name_es="Noche", slug_es="noche")
    link = CollectionPiece(piece=piece, collection=first)
    services.save_collection_piece(link, actor=user, request=request)
    link.collection = second
    services.save_collection_piece(link, actor=user, request=request)
    log = AuditLog.objects.filter(action="catalog.collections_updated").latest("pk")
    assert log.diff == {"Colecciones": [["Aurora"], ["Noche"]]}
    assert_context(log, user, piece)
    with pytest.raises(ValueError), transaction.atomic():
        services.delete_catalog_object(link, actor=user, request=request)
        raise ValueError("revertir")
    assert CollectionPiece.objects.filter(piece=piece).exists()
    assert AuditLog.objects.filter(action=log.action).count() == 2
    link = CollectionPiece.objects.get(piece=piece)
    services.delete_catalog_object(link, actor=user, request=request)
    assert AuditLog.objects.filter(action=log.action).latest("pk").diff == {
        "Colecciones": [["Noche"], []]
    }


@pytest.mark.parametrize("model", [Category, Stone, Collection, Material])
def test_taxonomy_lifecycle_context_diff_and_rollback(model):
    _, user = staff(PROPIETARIO)
    request = request_for(user)
    obj = model(name_es="Aurora", slug_es="aurora")
    services.save_taxonomy(obj, actor=user, request=request)
    action = f"catalog.{obj._meta.model_name}"
    log = AuditLog.objects.get(action=action + "_created")
    assert_context(log, user, obj)
    assert [None, "Aurora"] in log.diff.values()
    services.save_taxonomy(obj, actor=user, request=request)
    assert AuditLog.objects.filter(action=action + "_updated").count() == 0
    obj.name_es = "Noche"
    services.save_taxonomy(obj, actor=user, request=request)
    assert ["Aurora", "Noche"] in AuditLog.objects.get(action=action + "_updated").diff.values()
    pk = obj.pk
    with pytest.raises(ValueError), transaction.atomic():
        services.delete_catalog_object(obj, actor=user, request=request)
        raise ValueError("revertir")
    assert model.objects.filter(pk=pk).exists()
    assert not AuditLog.objects.filter(action=action + "_deleted").exists()
    obj = model.objects.get(pk=pk)
    services.delete_catalog_object(obj, actor=user, request=request)
    log = AuditLog.objects.get(action=action + "_deleted")
    assert log.object_id == str(pk) and ["Noche", None] in log.diff.values()


@pytest.mark.parametrize("model", [Category, Stone, Collection])
def test_cover_visual_editor_and_admin_use_same_audit(model, django_capture_on_commit_callbacks):
    browser, user = staff(PROPIETARIO)
    obj = model.objects.create(name_es="Anillos", slug_es="anillos")
    endpoint = reverse("visual-editor-action", args=["taxonomy-cover"])
    for size in [(100, 150), (150, 100)]:
        with django_capture_on_commit_callbacks(execute=True):
            response = browser.post(
                endpoint,
                {"model": model._meta.model_name, "id": obj.pk, "file": image_file(size=size)},
                HTTP_USER_AGENT="Prueba de catálogo",
                REMOTE_ADDR="127.0.0.8",
            )
        assert response.status_code == 200
    logs = AuditLog.objects.filter(action=f"catalog.{model._meta.model_name}_updated")
    assert logs.count() == 2
    log = logs.latest("pk")
    assert_context(log, user, obj)
    assert log.diff["Portada de Anillos"] == ["Portada anterior", "Portada reemplazada"]
    history = browser.get(reverse(f"admin:catalog_{model._meta.model_name}_history", args=[obj.pk]))
    assert "Portada de Anillos: Portada anterior → Portada reemplazada" in history.content.decode()
    obj.refresh_from_db()
    obj.cover_image = ""
    admin.site._registry[model].save_model(request_for(user), obj, None, True)
    assert logs.latest("pk").diff["Portada de Anillos"] == ["Portada anterior", "Sin portada"]


def test_quick_category_single_record():
    browser, user = staff(PROPIETARIO)
    response = browser.post(
        reverse("admin:catalog_category_quick_add"),
        {"name": "Anillos"},
        HTTP_USER_AGENT="Prueba de catálogo",
        REMOTE_ADDR="127.0.0.8",
    )
    obj = Category.objects.get(pk=response.json()["id"])
    logs = AuditLog.objects.filter(action="catalog.category_created")
    assert logs.count() == 1
    assert_context(logs.get(), user, obj)


def test_piece_delete_batch_audit_rolls_back(make_piece):
    _, user = staff(PROPIETARIO)
    first, second = make_piece(published=False), make_piece(published=False)
    ids = [first.pk, second.pk]
    original = Piece.delete

    def failing_delete(obj, *args, **kwargs):
        if obj.pk == second.pk:
            raise ValueError("fallo")
        return original(obj, *args, **kwargs)

    with patch.object(Piece, "delete", failing_delete), pytest.raises(ValueError):
        services.delete_pieces(
            Piece.objects.filter(pk__in=ids), actor=user, request=request_for(user)
        )
    assert Piece.objects.filter(pk__in=ids).count() == 2
    assert not AuditLog.objects.filter(action="catalog.piece_deleted").exists()
    services.delete_pieces(Piece.objects.filter(pk__in=ids), actor=user, request=request_for(user))
    assert AuditLog.objects.filter(action="catalog.piece_deleted", actor=user).count() == 2
    assert set(
        AuditLog.objects.filter(action="catalog.piece_deleted").values_list("object_id", flat=True)
    ) == set(map(str, ids))


def test_history_retains_permissions(make_piece):
    browser, user = staff(CONTENIDO)
    piece = make_piece(published=False)
    assert browser.get(reverse("admin:catalog_piece_history", args=[piece.pk])).status_code == 200
    user.groups.clear()
    assert browser.get(reverse("admin:catalog_piece_history", args=[piece.pk])).status_code == 403


def test_photo_admin_cannot_leave_published_piece_without_image(make_piece):
    browser, _ = staff("developer")
    piece = make_piece(published=False, status="published")
    photos = photos_for(piece, 2)
    primary = photos[0]
    delete_url = reverse("admin:catalog_pieceimage_delete", args=[primary.pk])
    response = browser.post(delete_url, {"post": "yes"}, follow=True)
    assert response.status_code == 200
    assert services.PUBLISHED_PHOTO_MESSAGE in response.content.decode()
    assert piece.images.filter(pk=primary.pk, is_primary=True).exists()
    assert not AuditLog.objects.filter(action="catalog.photos_updated").exists()
    # Metadata edits on the standalone photo screen also belong to the piece history.
    url = reverse("admin:catalog_pieceimage_change", args=[primary.pk])
    data = {
        "piece": piece.pk,
        "position": 0,
        "is_primary": "on",
        "alt_es": "Nueva descripción",
        "alt_en": "New description",
    }
    assert browser.post(url, data).status_code == 302
    log = AuditLog.objects.get(action="catalog.photos_updated")
    assert any(pair == ["Foto 0", "Nueva descripción"] for pair in log.diff.values())
    assert log.object_id == str(piece.pk)


def test_history_lines_are_readable_for_the_owner(make_piece):
    from types import SimpleNamespace

    from apps.catalog.audit_history import describe_event
    from apps.catalog.models import Category, PieceImage

    piece = make_piece(published=False)
    parent = Category.objects.create(name_es="Anillos", slug_es="anillos-hist")
    child = Category.objects.create(name_es="Solitarios", slug_es="solitarios-hist", parent=parent)
    first = PieceImage.objects.create(piece=piece, original="a.webp", alt_es="Frente", position=0)
    second = PieceImage.objects.create(piece=piece, original="b.webp", alt_es="Lado", position=1)
    event = SimpleNamespace(
        action="catalog.piece_updated",
        diff={
            "id": [None, piece.pk],
            "care": [None, ""],
            "category": [None, child.pk],
            "price_cents": [100000, 250000],
            "principal": [first.pk, second.pk],
        },
    )
    lines = describe_event(event)
    text = "\n".join(lines)
    assert "Categoría: Sin valor → Anillos → Solitarios" in text
    assert "Precio: $1.000 → $2.500" in text
    assert "Foto 1 (Frente) → Foto 2 (Lado)" in text
    assert "Cuidados" not in text and "ID" not in text
