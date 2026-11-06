import pytest
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import Client, RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.roles import CONTENIDO, PROPIETARIO
from apps.audit.models import AuditLog
from apps.catalog.models import Category, Piece
from apps.catalog.tests.conftest import image_file
from apps.catalog.tests.test_photo_management import photos_for
from apps.catalog.tests.test_stage3 import change_data
from apps.core.tests.test_dashboard_client import staff

pytestmark = pytest.mark.django_db


def quick_url():
    return reverse("admin:catalog_category_quick_add")


def test_quick_create_hierarchy_audit():
    browser, user = staff(PROPIETARIO)
    root_response = browser.post(quick_url(), {"name": "Anillos"})
    assert root_response.status_code == 200
    root = root_response.json()
    assert set(root) == {"id", "label"} and root["label"] == "Anillos"
    response = browser.post(quick_url(), {"name": "Solitarios", "parent": root["id"]})
    assert response.json()["label"] == "Anillos → Solitarios"
    child = Category.objects.get(pk=response.json()["id"])
    assert child.slug_es == "solitarios" and child.parent_id == root["id"]
    assert AuditLog.objects.filter(action="catalog.category_created", actor=user).count() == 2
    invalid = browser.post(quick_url(), {"name": "Tercer nivel", "parent": child.pk})
    assert invalid.status_code == 400 and "parent" in invalid.json()["errors"]
    duplicate = browser.post(quick_url(), {"name": "Solitarios", "parent": root["id"]})
    assert duplicate.status_code == 400
    assert duplicate.json()["errors"]["name"] == ["Ya existe «Solitarios» dentro de Anillos."]
    empty = browser.post(quick_url(), {"name": "  "})
    assert empty.status_code == 400 and "name" in empty.json()["errors"]
    assert browser.get(quick_url()).status_code == 405


def test_quick_same_name_different_parent_and_inactive():
    browser, _ = staff(PROPIETARIO)
    root = Category.objects.create(name_es="Raíz", slug_es="raiz")
    inactive = Category.objects.create(name_es="Inactiva", slug_es="inactiva", is_active=False)
    assert browser.post(quick_url(), {"name": "Igual"}).status_code == 200
    assert browser.post(quick_url(), {"name": "Igual", "parent": root.pk}).status_code == 200
    assert browser.post(quick_url(), {"name": "Hija", "parent": inactive.pk}).status_code == 400


def test_permissions_button_csrf():
    browser, user = staff(CONTENIDO)
    permission = Permission.objects.get(codename="add_category", content_type__app_label="catalog")
    # Use direct permissions to isolate the exact capability from managed roles.
    user.groups.clear()
    user.user_permissions.set(
        Permission.objects.filter(
            codename__in=["view_piece", "change_piece"], content_type__app_label="catalog"
        )
    )
    piece = Piece.objects.create(sku="BUTTON", name_es="Pieza", slug_es="pieza", price_cents=10000)
    url = reverse("admin:catalog_piece_change", args=[piece.pk])
    assert b"data-category-open" not in browser.get(url).content
    assert browser.post(quick_url(), {"name": "Prohibida"}).status_code == 403
    user.user_permissions.add(permission)
    assert b"data-category-open" in browser.get(url).content
    csrf = Client(enforce_csrf_checks=True)
    csrf.cookies = browser.cookies
    assert csrf.post(quick_url(), {"name": "Sin token"}).status_code == 403
    csrf.get(url)
    assert (
        csrf.post(
            quick_url(),
            {"name": "Con token", "csrfmiddlewaretoken": csrf.cookies["csrftoken"].value},
        ).status_code
        == 200
    )


def test_categories_order_count_queries_and_parent(make_piece):
    browser, user = staff(PROPIETARIO)
    root = Category.objects.create(name_es="Anillos", slug_es="anillos", position=1)
    child = Category.objects.create(
        name_es="Solitarios", slug_es="solitarios", parent=root, position=8
    )
    other = Category.objects.create(name_es="Collares", slug_es="collares", position=2)
    published = make_piece(published=True)
    published.category = child
    published.save(update_fields=["category"])
    draft = make_piece(published=False)
    draft.category = child
    draft.save(update_fields=["category"])
    model_admin = admin.site._registry[Category]
    request = RequestFactory().get("/")
    request.user = user
    with CaptureQueriesContext(connection) as queries:
        rows = list(model_admin.get_queryset(request))
        for row in rows:
            model_admin.hierarchical_name(row)
            model_admin.category_actions(row)
            str(row.parent) if row.parent_id else None
    assert len(queries) <= 2
    assert [row.pk for row in rows] == [root.pk, child.pk, other.pk]
    assert rows[1].published_total == 1 and rows[0].published_total == 0
    with CaptureQueriesContext(connection) as small_queries:
        response = browser.get(reverse("admin:catalog_category_changelist"))
    assert response.status_code == 200
    assert [row.pk for row in response.context["cl"].result_list] == [root.pk, child.pk, other.pk]
    html = response.content.decode()
    assert 'aria-label="Editar"' in html and 'aria-label="Ver en la tienda"' in html
    for index in range(20):
        Category.objects.create(name_es=f"Otra {index}", slug_es=f"otra-{index}", parent=other)
    with CaptureQueriesContext(connection) as many_queries:
        larger_response = browser.get(reverse("admin:catalog_category_changelist"))
    assert larger_response.status_code == 200
    assert len(many_queries) < 35
    assert len(many_queries) <= len(small_queries) + 2
    category_form = model_admin.get_form(request, obj=root)(instance=root)
    assert list(category_form.fields["parent"].queryset) == [other]
    child_form = model_admin.get_form(request, obj=child)(instance=child)
    assert set(child_form.fields["parent"].queryset) == {root, other}


def test_photo_replacement_markup_and_post(make_piece):
    browser, _ = staff(PROPIETARIO)
    piece = make_piece(published=False)
    photo = photos_for(piece, 1)[0]
    old_name = photo.original.name
    url, data = change_data(browser, piece)
    html = browser.get(url).content.decode()
    assert "Reemplazar foto" in html and 'for="id_images-0-original"' in html
    assert 'name="images-0-original"' in html
    assert 'name="images-0-original-clear"' not in html
    assert "Descripción de la foto (para accesibilidad y Google)" in html
    assert "Descripción en inglés (opcional)" in html
    assert (
        "related-widget-wrapper"
        not in html.split("ca-photo-original")[1].split("ca-photo-field")[0]
    )
    data["images-0-original"] = image_file(size=(20, 20))
    response = browser.post(url, data)
    assert response.status_code == 302, response.context and response.context["errors"]
    photo.refresh_from_db()
    assert photo.original.name != old_name
