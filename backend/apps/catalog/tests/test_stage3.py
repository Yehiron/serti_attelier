from unittest.mock import patch

import pytest
from django.contrib import admin
from django.db import IntegrityError, connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.roles import CONTENIDO, PROPIETARIO
from apps.catalog import services
from apps.catalog.api.serializers import PieceDetailSerializer
from apps.catalog.models import Category, Piece
from apps.catalog.tests.test_admin_sections import add_data
from apps.catalog.tests.test_operating_rules import change_data as original_change_data
from apps.catalog.tests.test_photo_management import photos_for
from apps.core.tests.test_dashboard_client import staff

pytestmark = pytest.mark.django_db


def change_data(browser, piece):
    url, data = original_change_data(browser, piece)
    return url, {k: "" if v is None else v for k, v in data.items()}


def category():
    return Category.objects.create(name_es="Anillos", slug_es="anillos")


def create_piece(sku="", cat=None, name="Uno"):
    piece = Piece(sku=sku, name_es=name, slug_es=name.lower(), category=cat, price_cents=10000)
    return services.save_piece(piece, actor=None)


def test_auto_sku_sequence_and_manual():
    root = category()
    child = Category.objects.create(name_es="Solitarios", slug_es="solitarios", parent=root)
    assert create_piece(cat=child).sku == "SRT-ANI-0001"
    assert create_piece(cat=root, name="Dos").sku == "SRT-ANI-0002"
    assert create_piece(name="Tres").sku == "SRT-GEN-0001"
    assert create_piece("MANUAL", root, "Cuatro").sku == "MANUAL"


def test_sku_collision_retry():
    root = category()
    original_save = Piece.save
    attempts = []

    def collision(piece, *args, **kwargs):
        if piece.sku.startswith("SRT-") and not attempts:
            attempts.append(piece.sku)
            raise IntegrityError("sku collision")
        return original_save(piece, *args, **kwargs)

    # A competing transaction's committed reference is visible after the failed savepoint.
    real_exists = Piece.objects.filter(sku="absent").__class__.exists

    def exists(queryset):
        if attempts and "SRT-ANI-0001" in str(queryset.query):
            return True
        return real_exists(queryset)

    with (
        patch.object(Piece, "save", collision),
        patch("django.db.models.query.QuerySet.exists", exists),
        patch("apps.catalog.services.next_piece_sku", side_effect=["SRT-ANI-0001", "SRT-ANI-0002"]),
    ):
        assert create_piece(cat=root).sku == "SRT-ANI-0002"


def test_add_form_empty_sku():
    browser, _ = staff(PROPIETARIO)
    url = reverse("admin:catalog_piece_add")
    data = add_data(browser.get(url)) | {"sku": "", "category": category().pk}
    response = browser.post(url, data)
    assert response.status_code == 302
    assert Piece.objects.get().sku == "SRT-ANI-0001"


def test_attributes_post_and_public_contract():
    browser, _ = staff(PROPIETARIO)
    piece = create_piece("ATTR")
    Piece.objects.filter(pk=piece.pk).update(attributes={"legacy": {"keep": True}, "ring_size": 7})
    piece.refresh_from_db()
    url, data = change_data(browser, piece)
    expected = {
        "legacy": {"keep": True},
        "metal": "Oro",
        "metal_purity": "18k",
        "ring_size": 7,
        "length_mm": 42.5,
        "dimensions_mm": "12 x 8",
        "weight_g": 3.2,
        "carats": 0.4,
    }
    response = browser.post(url, data | {k: str(v) for k, v in expected.items() if k != "legacy"})
    assert response.status_code == 302
    piece.refresh_from_db()
    assert piece.attributes == expected
    assert PieceDetailSerializer(piece, context={"locale": "es"}).data["attributes"] == expected


@pytest.mark.parametrize("field", ["length_mm", "weight_g", "carats", "ring_size"])
def test_attributes_reject_negative(field):
    browser, _ = staff(PROPIETARIO)
    piece = create_piece("NEG")
    url, data = change_data(browser, piece)
    response = browser.post(url, data | {field: "-1"})
    assert response.status_code == 200
    assert field in response.context["adminform"].form.errors
    piece.refresh_from_db()
    assert piece.attributes == {}


def test_list_tabs_pagination_actions_and_empty():
    browser, _ = staff(PROPIETARIO)
    url = reverse("admin:catalog_piece_changelist")
    assert "Aún no tienes piezas" in browser.get(url).content.decode()
    root = category()
    for i in range(27):
        Piece.objects.create(
            sku=f"L{i}",
            name_es=f"Anillo {i}",
            slug_es=f"anillo-{i}",
            category=root,
            price_cents=10000,
            status="published" if i == 0 else "draft",
        )
    response = browser.get(url)
    html = response.content.decode()
    assert len(response.context["cl"].result_list) == 25
    assert {t["label"]: t["count"] for t in response.context["piece_tabs"]} == {
        "Todas": 27,
        "Borradores": 26,
        "Publicadas": 1,
        "Ocultas": 0,
        "Archivadas": 0,
    }
    assert 'aria-label="Editar"' in html and 'aria-label="Duplicar"' in html
    assert 'aria-label="Publicar"' in html and "⋮" not in html
    assert not admin.site._registry[Piece].actions_row
    published = browser.get(
        url, {"status__exact": "published", "q": "Anillo", "category__id__exact": root.pk}
    )
    assert published.context["cl"].result_count == 1
    assert 'aria-label="Ver en la tienda"' in published.content.decode()
    drafts = browser.get(url, {"status__exact": "draft"})
    assert 'aria-label="Ver en la tienda"' not in drafts.content.decode()
    assert drafts.context["piece_tabs"][0]["count"] == 27
    assert "Limpiar filtros" in browser.get(url, {"q": "nada"}).content.decode()
    assert (
        "No encontramos piezas con estos filtros."
        in browser.get(url, {"q": "nada"}).content.decode()
    )


def test_list_queries_bounded():
    browser, _ = staff(PROPIETARIO)
    root = category()
    url = reverse("admin:catalog_piece_changelist")

    def add(index):
        piece = create_piece(f"Q{index}", root, f"Q{index}")
        photos_for(piece, 3)

    add(0)
    browser.get(url)  # warm non-catalog caches
    with CaptureQueriesContext(connection) as one:
        browser.get(url)
    for i in range(1, 25):
        add(i)
    with CaptureQueriesContext(connection) as many:
        response = browser.get(url)
    assert len(many) <= len(one) + 2
    assert len(many) < 35
    assert all(len(piece.list_primary_images) == 1 for piece in response.context["cl"].result_list)
    photo_queries = [q["sql"] for q in many if 'FROM "catalog_pieceimage"' in q["sql"]]
    assert len(photo_queries) == 1 and "is_primary" in photo_queries[0]


def test_checklist_and_content_permissions():
    browser, _ = staff(CONTENIDO)
    piece = create_piece("READ")
    photos_for(piece, 1)
    url, data = change_data(browser, piece)
    page = browser.get(url)
    html = page.content.decode()
    assert "Lista para publicar" in html and "Detalles de la pieza" in html
    assert "Foto principal" in html and "data-photo-card" in html
    assert 'name="catalog_piece_save_publish"' not in html
    assert 'aria-label="Eliminar foto"' not in html
    assert 'name="price_cents"' not in html
    checks = {check["label"]: check["ready"] for check in page.context["publication_checklist"]}
    assert checks["Nombre"] and checks["Foto principal"] and not checks["Categoría"]
    assert page.context["publication_missing"] == services.publication_missing(piece)
    assert browser.post(url, data | {"price_cents": "999"}).status_code == 302
    piece.refresh_from_db()
    assert piece.price_cents == 10000
    listing = browser.get(reverse("admin:catalog_piece_changelist")).content.decode()
    assert 'aria-label="Duplicar"' not in listing and 'aria-label="Publicar"' not in listing


def test_grid_post_swaps_flags_and_order():
    browser, _ = staff(PROPIETARIO)
    piece = create_piece("GRID")
    images = photos_for(piece, 2)
    url, data = change_data(browser, piece)
    assert "data-photo-card" in browser.get(url).content.decode()
    for i in range(2):
        data.pop(f"images-{i}-is_primary", None)
        data.pop(f"images-{i}-is_hover", None)
        data[f"images-{i}-position"] = 1 - i
    data.update({"images-1-is_primary": "on", "images-0-is_hover": "on"})
    assert browser.post(url, data).status_code == 302
    assert piece.images.get(is_primary=True).pk == images[1].pk
    assert piece.images.get(is_hover=True).pk == images[0].pk
    assert list(piece.images.values_list("pk", flat=True)) == [images[1].pk, images[0].pk]


@pytest.mark.django_db(transaction=True)
def test_concurrent_first_skus_postgresql():
    if connection.vendor != "postgresql":
        pytest.skip("La concurrencia del SKU requiere PostgreSQL")
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections

    root = category()
    barrier = Barrier(2)

    def create(index):
        close_old_connections()
        try:
            cat = Category.objects.get(pk=root.pk)
            barrier.wait(timeout=10)
            return create_piece(cat=cat, name=f"Concurrente-{index}").sku
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert set(pool.map(create, [1, 2])) == {"SRT-ANI-0001", "SRT-ANI-0002"}


def test_view_only_grid_has_no_edit_controls():
    from django.contrib.auth.models import Permission

    browser, user = staff(CONTENIDO)
    user.groups.clear()
    user.user_permissions.add(
        *Permission.objects.filter(codename__in=["view_piece", "view_pieceimage"])
    )
    piece = create_piece("VIEW")
    photos_for(piece, 1)
    html = browser.get(reverse("admin:catalog_piece_change", args=[piece.pk])).content.decode()
    assert "data-photo-card" in html
    assert "data-photo-move=" not in html
    assert 'name="new_photos"' not in html
    assert 'name="_continue"' not in html


def test_category_path_and_upload_error_message():
    from apps.core.tests.test_one_page_actions import photo

    browser, _ = staff(PROPIETARIO)
    root = category()
    Category.objects.create(name_es="Solitarios", slug_es="solitarios", parent=root)
    url = reverse("admin:catalog_piece_add")
    page = browser.get(url)
    assert "Anillos → Solitarios" in page.content.decode()
    data = add_data(page) | {"new_photos": photo("anillo.png"), "price_cents": "-1"}
    response = browser.post(url, data)
    assert response.status_code == 200
    assert (
        "Vuelve a elegir las fotos nuevas: el navegador no permite conservarlas tras un error."
        in response.content.decode()
    )
    assert not Piece.objects.exists()
