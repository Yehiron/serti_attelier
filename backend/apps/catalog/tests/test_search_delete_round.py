import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.roles import CONTENIDO, PROPIETARIO
from apps.audit.models import AuditLog
from apps.catalog import services
from apps.catalog.models import Category, Collection, Piece, Stone
from apps.cms.selectors import home_categories
from apps.core.tests.test_dashboard_client import staff

pytestmark = pytest.mark.django_db


def category(name="Gorras", **kwargs):
    return Category.objects.create(name_es=name, slug_es=name.lower(), **kwargs)


@pytest.mark.parametrize("role,visible", [(PROPIETARIO, True), (CONTENIDO, False)])
def test_delete_permissions(role, visible):
    browser, _ = staff(role)
    cat = category()
    Piece.objects.create(name_es="Anillo X", slug_es="anillo-x", sku="R1", price_cents=10000)
    for model, label in [("piece", "Eliminar pieza"), ("category", "Eliminar categoría")]:
        response = browser.get(reverse(f"admin:catalog_{model}_changelist"))
        assert response.status_code == 200
        assert (f'aria-label="{label}"' in response.content.decode()) is visible
    assert cat.pk


def test_protected_icons_and_no_category_bulk():
    browser, _ = staff(PROPIETARIO)
    cat = category()
    Piece.objects.create(
        name_es="Anillo X",
        slug_es="anillo-x",
        sku="R1",
        price_cents=10000,
        category=cat,
        sale_state="sold",
    )
    response = browser.get(reverse("admin:catalog_category_changelist"))
    html = response.content.decode()
    assert "Tiene 1 pieza" in html
    assert 'aria-disabled="true"' in html
    assert 'name="_selected_action"' not in html
    assert 'name="action"' not in html
    html = browser.get(reverse("admin:catalog_piece_changelist")).content.decode()
    assert "está vendida o reservada" in html
    assert "Archívala" in html


@pytest.mark.parametrize("model", [Category, Stone, Collection])
def test_confirm_csrf_and_audit(model):
    browser, user = staff(PROPIETARIO)
    obj = model.objects.create(name_es="Prueba", slug_es="prueba")
    url = reverse(f"admin:catalog_{model._meta.model_name}_delete", args=[obj.pk])
    secure = Client(enforce_csrf_checks=True)
    secure.cookies = browser.cookies
    response = secure.get(url)
    assert response.status_code == 200
    assert "Esta acción no se puede deshacer" in response.content.decode()
    assert secure.post(url, {"post": "yes"}).status_code == 403
    token = secure.cookies["csrftoken"].value
    assert secure.post(url, {"post": "yes", "csrfmiddlewaretoken": token}).status_code == 302
    assert not model.objects.filter(pk=obj.pk).exists()
    assert AuditLog.objects.filter(
        action=f"catalog.{model._meta.model_name}_deleted", actor=user
    ).exists()


def test_piece_confirmation_audit_and_protection():
    browser, user = staff(PROPIETARIO)
    piece = Piece.objects.create(
        name_es="Anillo X", slug_es="anillo-x", sku="R1", price_cents=10000
    )
    url = reverse("admin:catalog_piece_delete", args=[piece.pk])
    secure = Client(enforce_csrf_checks=True)
    secure.cookies = browser.cookies
    assert "¿Eliminar «Anillo X»?" in secure.get(url).content.decode()
    assert secure.post(url, {"post": "yes"}).status_code == 403
    assert (
        secure.post(
            url, {"post": "yes", "csrfmiddlewaretoken": secure.cookies["csrftoken"].value}
        ).status_code
        == 302
    )
    assert AuditLog.objects.filter(action="catalog.piece_deleted", actor=user).exists()


@pytest.mark.parametrize("model", ["catalog_piece", "orders_order"])
def test_optional_selection(model):
    browser, _ = staff(PROPIETARIO)
    for query in ("", "?select=1"):
        response = browser.get(reverse(f"admin:{model}_changelist") + query)
        assert response.status_code == 200
        assert "core/selection.js" in response.content.decode()
        assert "core/selection.css" in response.content.decode()
        assert response.context["cl"].get_filters_params().get("select") is None
        if query:
            assert "select=1" in response.context["cl"].get_query_string()


def test_empty_category_visible_and_append_position():
    cat = category(position=8)
    new = Category(name_es="Nueva", slug_es="nueva")
    services.save_taxonomy(new)
    assert new.position == 9
    assert cat.position == 8
    assert {item["slug"] for item in home_categories("es")} >= {"gorras", "nueva"}
    browser, _ = staff(PROPIETARIO)
    assert (
        "Visible en la tienda · sin piezas publicadas"
        in browser.get(reverse("admin:catalog_category_changelist")).content.decode()
    )
    response = browser.get("/api/v1/catalog/taxonomy?locale=en")
    assert "gorras" in str(response.data)
    assert (
        "aunque no tengan piezas ni foto"
        in browser.get(reverse("admin:catalog_category_change", args=[cat.pk])).content.decode()
    )
    cat.is_active = False
    cat.save()
    assert "gorras" not in {item["slug"] for item in home_categories("es")}


def test_children_protected_on_confirmation():
    browser, _ = staff(PROPIETARIO)
    root = category()
    category("Hija", parent=root)
    url = reverse("admin:catalog_category_delete", args=[root.pk])
    assert "Tiene subcategorías" in browser.get(url).content.decode()
    assert browser.post(url, {"post": "yes"}).status_code == 200
    assert Category.objects.filter(pk=root.pk).exists()


@pytest.mark.parametrize("model", [Stone, Collection])
def test_linked_taxonomy_has_no_bulk_and_blocks_delete(model):
    browser, _ = staff(PROPIETARIO)
    obj = model.objects.create(name_es="Vinculada", slug_es="vinculada")
    piece = Piece.objects.create(name_es="Anillo", slug_es="anillo", sku="LINK", price_cents=1)
    if model is Stone:
        piece.stones.add(obj)
    else:
        piece.collections.add(obj)
    html = browser.get(
        reverse(f"admin:catalog_{model._meta.model_name}_changelist")
    ).content.decode()
    assert "Tiene piezas: retíralas antes de eliminarla" in html
    assert 'name="_selected_action"' not in html
    url = reverse(f"admin:catalog_{model._meta.model_name}_delete", args=[obj.pk])
    assert browser.post(url, {"post": "yes"}).status_code == 200
    assert model.objects.filter(pk=obj.pk).exists()
