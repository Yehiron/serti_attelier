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
        assert (
            (f'aria-label="{label}"' in response.content.decode())
            if model == "piece"
            else ("Eliminar…" in response.content.decode())
        ) is visible
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
    assert reverse("admin:catalog_category_delete", args=[cat.pk]) in html
    assert 'name="_selected_action"' not in html
    assert 'name="action"' not in html
    html = browser.get(reverse("admin:catalog_piece_changelist")).content.decode()
    assert "está vendida o reservada" not in html


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
    html = secure.get(url).content.decode()
    assert "Anillo X" in html and "R1" in html and "Eliminar" in html
    assert secure.post(url, {"action": "delete", "sku": "R1"}).status_code == 403
    token = secure.cookies["csrftoken"].value
    assert (
        secure.post(
            url, {"action": "delete", "sku": "R1", "csrfmiddlewaretoken": token}
        ).status_code
        == 302
    )
    assert not Piece.objects.filter(pk=piece.pk).exists()
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
        "Sin piezas publicadas o sin portada"
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
    child = category("Hija", parent=root)
    url = reverse("admin:catalog_category_delete", args=[root.pk])
    html = browser.get(url).content.decode()
    assert "Primero resuelve sus subcategorías" in html
    assert "Hija" in html
    assert reverse("admin:catalog_category_change", args=[child.pk]) in html
    assert 'name="post"' not in html
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
    changelist = reverse(f"admin:catalog_{model._meta.model_name}_changelist")
    if model is Stone:
        # Stones use the list-detail screen: «Eliminar…» lives in the selected stone's panel.
        html = browser.get(f"{changelist}?stone={obj.pk}").content.decode()
    else:
        html = browser.get(changelist).content.decode()
        assert "Tiene 1 pieza: retírala antes de eliminarla" in html
    assert reverse(f"admin:catalog_{model._meta.model_name}_delete", args=[obj.pk]) in html
    assert 'name="_selected_action"' not in html
    url = reverse(f"admin:catalog_{model._meta.model_name}_delete", args=[obj.pk])
    html = browser.get(url).content.decode()
    assert all(value in html for value in ("LINK", "Anillo", "Borrador"))
    assert reverse("admin:catalog_piece_change", args=[piece.pk]) in html
    assert ("Piedras" if model is Stone else "Colecciones") in html
    assert 'name="post"' not in html
    assert browser.post(url, {"post": "yes"}).status_code == 200
    assert model.objects.filter(pk=obj.pk).exists()


def resolver(obj):
    return reverse(f"admin:catalog_{obj._meta.model_name}_resolve_deletion", args=[obj.pk])


def make_piece(index, **kwargs):
    return Piece.objects.create(
        name_es=f"Pieza {index}",
        slug_es=f"pieza-{index}",
        sku=f"SKU{index}",
        price_cents=10000,
        **kwargs,
    )


def test_stone_mixed_plan_and_audit():
    browser, user = staff(PROPIETARIO)
    old = Stone.objects.create(name_es="Vieja", slug_es="vieja")
    new = Stone.objects.create(name_es="Rubí", slug_es="rubi")
    pieces = [make_piece(i) for i in range(3)]
    for piece in pieces:
        piece.stones.add(old)
    response = browser.post(
        resolver(old),
        {
            f"decision_{pieces[0].pk}": f"move:{new.pk}",
            f"decision_{pieces[1].pk}": "remove",
            f"decision_{pieces[2].pk}": "delete",
        },
    )
    assert response.url == reverse("admin:catalog_stone_changelist")
    assert list(pieces[0].stones.all()) == [new]
    assert not pieces[1].stones.exists()
    assert not Piece.objects.filter(pk=pieces[2].pk).exists()
    assert not Stone.objects.filter(pk=old.pk).exists()
    assert AuditLog.objects.filter(action="catalog.piece_deleted", actor=user).exists()


@pytest.mark.parametrize("invalid", ["missing", "published", "foreign", "destination", "same"])
def test_invalid_plan_rolls_back(invalid):
    browser, _ = staff(PROPIETARIO)
    old = Stone.objects.create(name_es="Vieja", slug_es="vieja")
    new = Stone.objects.create(name_es="Nueva", slug_es="nueva")
    first = make_piece(1)
    second = make_piece(2, status="published" if invalid == "published" else "draft")
    foreign = make_piece(3)
    first.stones.add(old)
    second.stones.add(old)
    data = {f"decision_{first.pk}": f"move:{new.pk}", f"decision_{second.pk}": "remove"}
    if invalid == "missing":
        del data[f"decision_{second.pk}"]
    elif invalid == "published":
        data[f"decision_{second.pk}"] = "delete"
    elif invalid == "foreign":
        data[f"decision_{foreign.pk}"] = "remove"
    elif invalid == "destination":
        data[f"decision_{second.pk}"] = "move:999999"
    else:
        data[f"decision_{second.pk}"] = f"move:{old.pk}"
    browser.post(resolver(old), data)
    assert Stone.objects.filter(pk=old.pk).exists()
    assert list(first.stones.all()) == [old]
    assert list(second.stones.all()) == [old]


def test_collection_remove_all():
    browser, _ = staff(PROPIETARIO)
    obj = Collection.objects.create(name_es="Colección", slug_es="coleccion")
    pieces = [make_piece(i) for i in range(2)]
    obj.pieces.add(*pieces)
    browser.post(resolver(obj), {f"decision_{p.pk}": "remove" for p in pieces})
    assert not Collection.objects.filter(pk=obj.pk).exists()


def test_category_move_and_children():
    browser, _ = staff(PROPIETARIO)
    old = category("Origen")
    child = category("Hija", parent=old)
    target = category("Destino")
    piece = make_piece(1, category=old)
    html = browser.get(reverse("admin:catalog_category_delete", args=[old.pk])).content.decode()
    assert f'value="move:{child.pk}"' not in html
    assert "Primero resuelve sus subcategorías" in html
    browser.post(resolver(old), {f"decision_{piece.pk}": f"move:{target.pk}"})
    piece.refresh_from_db()
    assert piece.category_id == old.pk
    child.delete()
    browser.post(resolver(old), {f"decision_{piece.pk}": f"move:{target.pk}"})
    piece.refresh_from_db()
    assert piece.category_id == target.pk
    assert not Category.objects.filter(pk=old.pk).exists()


def test_guide_options_and_permissions():
    browser, _ = staff(PROPIETARIO)
    obj = Stone.objects.create(name_es="Piedra", slug_es="piedra")
    target = Stone.objects.create(name_es="Rubí", slug_es="rubi")
    draft = make_piece(1)
    published = make_piece(2, status="published")
    draft.stones.add(obj)
    published.stones.add(obj)
    url = reverse("admin:catalog_stone_delete", args=[obj.pk])
    html = browser.get(url).content.decode()
    assert all(text in html for text in ("SKU1", "Pieza 1", "Cambiar a Rubí", "Aplicar y eliminar"))
    assert f'value="move:{target.pk}"' in html
    assert html.count('<option value="delete">Eliminar la pieza</option>') == 1
    restricted, _ = staff(CONTENIDO)
    assert restricted.post(resolver(obj), {f"decision_{draft.pk}": "remove"}).status_code == 403
