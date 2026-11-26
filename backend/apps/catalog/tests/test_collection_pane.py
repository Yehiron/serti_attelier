import json

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse

from apps.accounts.roles import PROPIETARIO
from apps.audit.models import AuditLog
from apps.catalog.models import Collection, CollectionPiece, Piece
from apps.core.tests.test_dashboard_client import staff

pytestmark = pytest.mark.django_db


def piece(sku, **kwargs):
    return Piece.objects.create(
        name_es=sku, slug_es=sku.lower(), sku=sku, price_cents=390000000, **kwargs
    )


def post_curate(browser, collection, ids):
    return browser.post(
        reverse("admin:catalog_collection_curate"),
        json.dumps({"collection": collection.pk, "pieces": ids}),
        content_type="application/json",
    )


def test_render_selection_and_dialog():
    browser, _ = staff(PROPIETARIO)
    first = Collection.objects.create(name_es="Primera", slug_es="primera", position=0)
    second = Collection.objects.create(name_es="Segunda", slug_es="segunda", position=1)
    a, b = piece("AA-1"), piece("BB-1")
    CollectionPiece.objects.create(collection=second, piece=a, position=1)
    CollectionPiece.objects.create(collection=second, piece=b, position=0)
    url = reverse("admin:catalog_collection_changelist")
    response = browser.get(url + f"?collection={second.pk}")
    assert response.status_code == 200
    assert response.context["selected"] == second
    assert [p["id"] for p in response.context["selected_data"]] == [b.pk, a.pk]
    assert "Primera" in response.content.decode() and "collection-grid" in response.content.decode()
    assert browser.get(url).context["selected"] == first
    response = browser.get(url + "?collection=new")
    assert response.context["creating"] and b"data-auto-open" in response.content


def test_create_edit_and_errors():
    browser, _ = staff(PROPIETARIO)
    url = reverse("admin:catalog_collection_changelist")
    payload = {
        "name_es": "Nueva",
        "description_es": "Descripción",
        "position": "0",
        "is_active": "on",
    }
    response = browser.post(url + "?collection=new", payload)
    assert response.status_code == 302
    obj = Collection.objects.get(name_es="Nueva")
    response = browser.post(url + f"?collection={obj.pk}", {**payload, "name_es": "Editada"})
    assert response.status_code == 302
    obj.refresh_from_db()
    assert obj.name_es == "Editada"
    response = browser.post(url + f"?collection={obj.pk}", {**payload, "name_es": ""})
    assert response.status_code == 200 and response.context["pane_form"].errors
    assert b"data-auto-open" in response.content


def test_curate_add_remove_order_and_audit():
    browser, _ = staff(PROPIETARIO)
    collection = Collection.objects.create(name_es="Mesa", slug_es="mesa")
    a, b, c = piece("AA-2"), piece("BB-2"), piece("CC-2")
    CollectionPiece.objects.create(collection=collection, piece=a, position=0)
    CollectionPiece.objects.create(collection=collection, piece=b, position=1)
    response = post_curate(browser, collection, [b.pk, c.pk])
    assert response.json() == {"ok": True, "count": 2}
    assert list(
        CollectionPiece.objects.filter(collection=collection).values_list("piece_id", "position")
    ) == [(b.pk, 0), (c.pk, 1)]
    assert AuditLog.objects.filter(
        action="catalog.collection_curated", diff__Piezas=[["AA-2", "BB-2"], ["BB-2", "CC-2"]]
    ).exists()


def test_curate_rejects_invalid_and_checks_permission():
    browser, user = staff(PROPIETARIO)
    collection = Collection.objects.create(name_es="Mesa", slug_es="mesa")
    a = piece("AA-3")
    archived = piece("BB-3", status=Piece.Status.ARCHIVED)
    for ids in ([a.pk, a.pk], [99999999], [archived.pk], ["1"], [True]):
        assert post_curate(browser, collection, ids).status_code == 400
    user.groups.clear()
    user.user_permissions.add(Permission.objects.get(codename="view_collection"))
    assert post_curate(browser, collection, []).status_code == 403


def test_curate_keeps_archived_piece_already_in_collection():
    browser, _ = staff(PROPIETARIO)
    collection = Collection.objects.create(name_es="Mesa", slug_es="mesa")
    a = piece("AA-4")
    old = piece("BB-4", status=Piece.Status.ARCHIVED)
    CollectionPiece.objects.create(collection=collection, piece=old, position=0)
    CollectionPiece.objects.create(collection=collection, piece=a, position=1)
    assert post_curate(browser, collection, [a.pk, old.pk]).status_code == 200
    assert list(
        CollectionPiece.objects.filter(collection=collection).values_list("piece_id", flat=True)
    ) == [a.pk, old.pk]
