from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.roles import PROPIETARIO
from apps.audit.models import AuditLog
from apps.catalog.tests.test_stage3 import change_data
from apps.core.tests.test_dashboard_client import staff

pytestmark = pytest.mark.django_db


def test_piece_modal_get_and_list(make_piece):
    browser, _ = staff(PROPIETARIO)
    piece = make_piece(published=False)
    url = reverse("admin:catalog_piece_change", args=[piece.pk])
    listing = browser.get(reverse("admin:catalog_piece_changelist"))
    assert b"pe-dialog" in listing.content
    assert b'aria-label="Editar"' in listing.content
    response = browser.get(url + "?_modal=1")
    assert response.status_code == 200
    assert response["X-Frame-Options"] == "SAMEORIGIN"
    assert b"pe-editor" in response.content
    assert "Información" in response.content.decode()
    assert b"data-pe-completion" in response.content
    assert b"pe-editor" not in browser.get(url).content


def test_piece_modal_save_and_invalid(make_piece):
    browser, _ = staff(PROPIETARIO)
    piece = make_piece(published=False)
    url, data = change_data(browser, piece)
    data["name_es"] = "Pieza editada"
    response = browser.post(url + "?_modal=1", data)
    assert response.status_code == 200
    assert b"serti:piece-saved" in response.content
    piece.refresh_from_db()
    assert piece.name_es == "Pieza editada"
    assert AuditLog.objects.filter(object_id=str(piece.pk)).exists()
    data["name_es"] = ""
    response = browser.post(url + "?_modal=1", data)
    assert response.status_code == 200
    assert b"pe-editor" in response.content
    assert response.context["errors"]


def test_piece_modal_requires_permission(client, make_piece, django_user_model):
    piece = make_piece(published=False)
    user = django_user_model.objects.create_user(
        username="no-catalog", password="test", is_staff=True
    )
    client.force_login(user)
    url = reverse("admin:catalog_piece_change", args=[piece.pk]) + "?_modal=1"
    assert client.get(url).status_code == 403


def test_modal_chrome_actions_and_publication_requirements(make_piece):
    from apps.catalog import services

    browser, _ = staff(PROPIETARIO)
    piece = make_piece(published=False)
    response = browser.get(reverse("admin:catalog_piece_change", args=[piece.pk]) + "?_modal=1")
    html = response.content.decode()
    assert 'id="header"' not in html
    assert 'id="nav-sidebar"' not in html
    assert 'aria-label="Más acciones"' in html
    for label in ("Historial", "Marcar preventa", "Archivar", "Duplicar", "Eliminar"):
        assert label in html
    assert response.context["publication_missing"] == services.publication_missing(piece)
    assert "nombre en español" not in response.context["publication_missing"]
    assert 'id="pe-publication-missing"' in html


def test_modal_publish_hide_and_missing(make_piece):
    browser, _ = staff(PROPIETARIO)
    incomplete = make_piece(published=False)
    publish_url = reverse("admin:catalog_piece_detail_publish", args=[incomplete.pk])
    result = browser.post(publish_url, HTTP_ACCEPT="application/json")
    assert result.status_code == 400
    assert result.json()["missing"]
    incomplete.refresh_from_db()
    assert incomplete.status == "draft"

    piece = make_piece()
    hide_url = reverse("admin:catalog_piece_detail_hide", args=[piece.pk])
    result = browser.post(hide_url, HTTP_ACCEPT="application/json")
    assert result.status_code == 200
    assert result.json()["status"] == "hidden"
    result = browser.post(result.json()["toggle_url"], HTTP_ACCEPT="application/json")
    assert result.status_code == 200
    piece.refresh_from_db()
    assert piece.status == "published"


def test_modal_saves_preorder_through_inventory(make_piece):
    browser, _ = staff(PROPIETARIO)
    piece = make_piece(published=False)
    url, data = change_data(browser, piece)
    data["modal_sale_state"] = "preorder"
    response = browser.post(url + "?_modal=1", data)
    assert b"serti:piece-saved" in response.content
    piece.refresh_from_db()
    assert piece.sale_state == "preorder"
