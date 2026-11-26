import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.roles import CONTENIDO, PROPIETARIO
from apps.catalog.models import Category, Piece, Stone
from apps.catalog.tests.test_photo_management import photos_for
from apps.core.tests.test_dashboard_client import staff

pytestmark = pytest.mark.django_db


def piece(index, **kwargs):
    return Piece.objects.create(
        sku=f"V{index}",
        name_es=f"Pieza {index}",
        slug_es=f"v{index}",
        price_cents=index * 100000,
        **kwargs,
    )


def test_cards_chips_and_filters():
    browser, _ = staff(PROPIETARIO)
    root = Category.objects.create(name_es="Anillos", slug_es="anillos")
    child = Category.objects.create(name_es="Solitaire", slug_es="solitaire", parent=root)
    sold = piece(1, category=child, sale_state="sold")
    sold.stones.add(Stone.objects.create(name_es="Rubí", slug_es="rubi", color="#aa1234"))
    photos_for(sold, 1)
    other = piece(2, status="hidden")
    photos_for(other, 2)
    url = reverse("admin:catalog_piece_changelist")
    response = browser.get(url, {"q": "Pieza"})
    assert response.status_code == 200
    html = response.content.decode()
    for text in ("Pieza 1", "V1", "#aa1234", "Rubí", "1 foto", "Vendida"):
        assert text in html
    chips = {chip["label"]: chip for chip in response.context["showcase_chips"]}
    assert chips["Todas"]["count"] == 2
    assert chips["Anillos"]["count"] == 1
    assert chips["Vendidas"]["count"] == 1
    assert chips["Necesitan fotos"]["count"] == 1
    assert "q=Pieza" in chips["Anillos"]["url"]
    assert list(browser.get(url, {"category_root": root.pk}).context["cl"].result_list) == [sold]
    assert list(browser.get(url, {"health": "few_photos"}).context["cl"].result_list) == [sold]


def test_order_and_permissions():
    browser, _ = staff(PROPIETARIO)
    piece(1)
    piece(2)
    url = reverse("admin:catalog_piece_changelist")
    response = browser.get(url)
    options = dict(response.context["showcase_orders"])
    for label, expected in (
        ("Precio ↑", ["V1", "V2"]),
        ("Precio ↓", ["V2", "V1"]),
        ("Nombre A–Z", ["V1", "V2"]),  # noqa: RUF001
    ):
        value = next(k for k, v in options.items() if v == label)
        result = browser.get(url, {"o": value})
        assert result.status_code == 200
        assert [p.sku for p in result.context["cl"].result_list] == expected
    content_browser, _ = staff(CONTENIDO)
    cards = content_browser.get(url).context["showcase_cards"]
    assert all(not card["delete"] and not card["operations"] for card in cards)


def test_queries_do_not_grow_per_piece():
    browser, _ = staff(PROPIETARIO)
    url = reverse("admin:catalog_piece_changelist")
    for i in range(1, 4):
        piece(i)
    browser.get(url)
    with CaptureQueriesContext(connection) as small:
        assert browser.get(url).status_code == 200
    for i in range(4, 11):
        piece(i)
    with CaptureQueriesContext(connection) as large:
        assert browser.get(url).status_code == 200
    assert len(small) == len(large)
