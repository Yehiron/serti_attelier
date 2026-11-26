"""Presupuestos de consultas de las pantallas privadas, incluida su renderización."""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.roles import PROPIETARIO
from apps.catalog.models import Category, Collection, Piece, Stone
from apps.catalog.tests.test_photo_management import photos_for
from apps.core.tests.test_dashboard_client import staff

pytestmark = pytest.mark.django_db


def measured(browser, url, data=None):
    with CaptureQueriesContext(connection) as queries:
        response = browser.post(url, data) if data is not None else browser.get(url)
        assert response.status_code == 200
    return len(queries)


def test_query_budgets():
    browser, _ = staff(PROPIETARIO)
    root = Category.objects.create(name_es="Anillos", slug_es="anillos")
    pieces_url = reverse("admin:catalog_piece_changelist")
    categories_url = reverse("admin:catalog_category_changelist")
    editor_url = reverse("visual-editor") + "?tab=taxonomy"

    def add(start, end):
        for i in range(start, end):
            child = Category.objects.create(
                name_es=f"Categoría {i}", slug_es=f"cat-{i}", parent=root
            )
            piece = Piece.objects.create(
                sku=f"Q{i}",
                name_es=f"Pieza {i}",
                slug_es=f"q{i}",
                category=child,
                price_cents=10000,
            )
            photos_for(piece, 6)
            Stone.objects.create(name_es=f"Piedra {i}", slug_es=f"piedra-{i}")
            Collection.objects.create(name_es=f"Colección {i}", slug_es=f"coleccion-{i}")

    add(0, 5)
    piece = Piece.objects.first()
    detail_url = reverse("admin:catalog_piece_change", args=[piece.pk])
    status_url = reverse("admin:catalog_piece_photo_status", args=[piece.pk])
    urls = [pieces_url, detail_url, categories_url, status_url, editor_url]
    for url in urls:
        browser.get(url)  # cachés de permisos/content types fuera de la medición
    small = [measured(browser, url) for url in urls]
    ContentType.objects.get_for_model(Category)  # misma caché caliente en ambos POST
    quick_small = measured(
        browser,
        reverse("admin:catalog_category_quick_add"),
        {"name": "Nueva primera", "parent": root.pk},
    )
    add(5, 25)
    large = [measured(browser, url) for url in urls]
    quick = measured(
        browser, reverse("admin:catalog_category_quick_add"), {"name": "Nueva", "parent": root.pk}
    )
    print("CONSULTAS etapa 5", {"5": small, "25": large, "creación rápida": quick})
    # Presupuestos fijados después de medir; también congelan crecimiento cero por fila.
    assert small == large
    # La vitrina agrega consultas fijas (conteos de chips, categorías raíz, piedras); medido: 33.
    for count, budget in zip(large, [35, 35, 18, 15, 25], strict=True):
        assert count <= budget
    assert quick == quick_small
    assert quick <= 35


def test_piece_edit_checks_active_reservations_once():
    browser, _ = staff(PROPIETARIO)
    piece = Piece.objects.create(
        sku="RES-Q",
        name_es="Reservada",
        slug_es="reservada-q",
        price_cents=10000,
        sale_state="reserved",
    )
    url = reverse("admin:catalog_piece_change", args=[piece.pk])
    with CaptureQueriesContext(connection) as queries:
        assert browser.get(url).status_code == 200
    checks = [
        query
        for query in queries
        if 'SELECT 1 AS "a" FROM "inventory_piecereservation"' in query["sql"]
    ]
    # Each distinct reservation check (active hold, any history) may run once; none may repeat.
    sqls = [query["sql"] for query in checks]
    assert len(sqls) == len(set(sqls)) and len(sqls) <= 2
