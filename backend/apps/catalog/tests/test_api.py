from collections.abc import Callable
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from django.core.cache import cache
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.catalog.models import Category, Collection, CollectionPiece, Material, Piece, Stone
from apps.catalog.services import hide_pieces
from apps.core.selectors import get_solo
from apps.inventory.services import convert_reservation, reserve_piece, set_preorder

pytestmark = pytest.mark.django_db
URL = "/api/v1/catalog/pieces"


def test_availability_effective_price_facets_and_filters(
    client: Client, make_piece: Callable[..., Piece]
) -> None:
    stone = Stone.objects.create(
        name_es="Esmeralda", slug_es="esmeralda", name_en="Emerald", slug_en="emerald"
    )
    diamond = Stone.objects.create(name_es="Diamante", slug_es="diamante")
    material = Material.objects.create(name_es="Oro", slug_es="oro")
    collection = Collection.objects.create(name_es="Regalos", slug_es="regalos")
    child = Category.objects.create(
        name_es="Subcategoría",
        slug_es="sub",
        parent=Category.objects.create(name_es="Joyas", slug_es="joyas"),
    )
    first = make_piece(price_cents=200_000, sale_price_cents=50_000, is_new=True, category=child)
    first.stones.add(stone)
    first.materials.add(material)
    CollectionPiece.objects.create(collection=collection, piece=first)
    other = make_piece(price_cents=150_000)
    other.stones.add(diamond)
    sold = make_piece(price_cents=300_000)
    reservation = reserve_piece(
        sold.pk, kind="online", reference="sale", expires_at=timezone.now() + timedelta(minutes=30)
    )
    convert_reservation(reservation.pk, reason="payment_approved")
    assert client.get(URL).json()["count"] == 2
    assert client.get(URL, {"availability": "all"}).json()["count"] == 3
    response = client.get(URL, {"stone": "esmeralda", "price_max": "60000"}).json()
    assert [item["sku"] for item in response["results"]] == [first.sku]
    assert response["facets"]["price"] == {"min_cents": 50_000, "max_cents": 150_000}
    assert response["facets"]["stones"] == [
        {"slug": "esmeralda", "count": 1},
        {"slug": "diamante", "count": 1},
    ]
    for filters in [
        {"category": "joyas"},
        {"collection": "regalos"},
        {"material": "oro"},
        {"is_new": "true"},
        {"q": "Oro"},
        {"q": "Emerald"},
    ]:
        assert [item["sku"] for item in client.get(URL, filters).json()["results"]] == [first.sku]
    assert client.get(URL, {"stone": "esmeralda,diamante"}).json()["count"] == 2
    assert client.get(URL + "?stone=esmeralda&stone=diamante").json()["count"] == 2
    for sort, expected in [
        ("price_asc", [first.sku, other.sku]),
        ("price_desc", [other.sku, first.sku]),
        ("newest", [other.sku, first.sku]),
        ("featured", [first.sku, other.sku]),
    ]:
        assert [row["sku"] for row in client.get(URL, {"sort": sort}).json()["results"]] == expected


def test_locale_fallback_and_visibility(client: Client, make_piece: Callable[..., Piece]) -> None:
    piece = make_piece()
    es = client.get(URL, {"locale": "es"}).json()["results"][0]
    en = client.get(URL, HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9").json()["results"][0]
    assert (es["name"], es["slug"]) == ("Pieza 1", "pieza-1")
    assert (en["name"], en["slug"]) == ("Piece 1", "piece-1")
    assert client.get(URL + "/piece-1", {"locale": "en"}).status_code == 200
    Piece.objects.filter(pk=piece.pk).update(name_en="", slug_en="", short_description_en="")
    fallback = client.get(URL + "/pieza-1", {"locale": "en"})
    assert fallback.status_code == 200
    assert fallback.json()["name"] == "Pieza 1"
    hide_pieces(Piece.objects.filter(pk=piece.pk), None)
    detail = client.get(URL + "/pieza-1")
    assert detail.status_code == 404
    assert detail.headers["Content-Type"] == "application/problem+json"
    assert detail.json()["code"] == "piece_not_found"
    assert client.get(URL).json()["count"] == 0
    assert client.get(URL + "/status", {"skus": f"{piece.sku},missing"}).json() == {
        piece.sku: "unavailable",
        "missing": "unavailable",
    }


@pytest.mark.parametrize("state", ["available", "preorder", "reserved", "sold"])
@pytest.mark.parametrize("number", ["", "573001234567"])
def test_cta(client: Client, make_piece: Callable[..., Piece], state: str, number: str) -> None:
    piece = make_piece()
    config = get_solo()
    config.whatsapp_number = number
    config.save()
    if state == "preorder":
        set_preorder(piece, True, None)
    elif state in ("reserved", "sold"):
        reservation = reserve_piece(
            piece.pk,
            kind="online",
            reference="order",
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        if state == "sold":
            convert_reservation(reservation.pk, reason="payment_approved")
    with override_settings(PUBLIC_SITE_URL="https://example.com"):
        response = client.get(URL + "/piece-1", {"locale": "en"})
    assert response.status_code == 200
    data = response.json()
    assert data["seo"]["alternates"] == {
        "es": "https://example.com/es/piezas/pieza-1",
        "en": "https://example.com/en/pieces/piece-1",
    }
    if state == "available":
        assert data["cta"] == {"kind": "add_to_cart"}
    elif number:
        assert data["cta"]["reason"] == state
        url = urlparse(data["cta"]["url"])
        assert url.netloc == "wa.me"
        assert url.path == "/" + number
        text = parse_qs(url.query)["text"][0]
        assert "Piece 1" in text and piece.sku in text
        assert "https://example.com/en/pieces/piece-1" in text
    else:
        assert data["cta"] == {"kind": "whatsapp", "reason": state, "url": None}


def test_taxonomy_status_errors_and_throttle(
    client: Client, make_piece: Callable[..., Piece]
) -> None:
    piece = make_piece()
    Category.objects.create(name_es="Oculta", slug_es="oculta", is_active=False)
    taxonomy = client.get("/api/v1/catalog/taxonomy", {"locale": "en"}).json()
    assert taxonomy["categories"][0]["name"] == "Rings"
    assert len(taxonomy["categories"]) == 1
    assert client.get(URL + "/status", {"skus": piece.sku}).json() == {piece.sku: "available"}
    for params in [{"skus": ",".join(str(n) for n in range(51))}]:
        response = client.get(URL + "/status", params)
        assert response.status_code == 400
        assert response.json()["code"] == "validation_error"
    response = client.get(URL, {"price_min": "invalid"})
    assert response.status_code == 400
    assert set(response.json()) == {"type", "title", "status", "code", "detail"}
    cache.clear()
    with override_settings(PUBLIC_READ_RATE="1/min"):
        assert client.get(URL, HTTP_X_FORWARDED_FOR="spoof, 198.51.100.10").status_code == 200
        response = client.get(
            "/api/v1/locations/departments", HTTP_X_FORWARDED_FOR="changed, 198.51.100.10"
        )
        assert response.status_code == 429
        assert response.json()["code"] == "rate_limited"
        assert response.headers["Content-Type"] == "application/problem+json"
        assert "Retry-After" in response
    cache.clear()


def test_pagination_query_counts(client: Client, make_piece: Callable[..., Piece]) -> None:
    make_piece()
    with CaptureQueriesContext(connection) as small:
        response = client.get(URL)
        assert response.status_code == 200
    for _index in range(1, 50):
        make_piece(published=False, status="published", published_at=timezone.now())
    with CaptureQueriesContext(connection) as large:
        response = client.get(URL, {"page_size": 100})
        assert len(response.json()["results"]) == 48
    assert len(small) == len(large) == 8
    assert response.json()["next"] is not None
    assert client.get(URL).json()["count"] == 50
    assert len(client.get(URL).json()["results"]) == 24
    assert client.get(URL, {"page": 99}).status_code == 404


@pytest.mark.parametrize(
    "locale,slug,name", [("es", "pieza-1", "Pieza 1"), ("en", "piece-1", "Piece 1")]
)
def test_available_detail_uses_edited_general_whatsapp_template(
    client, make_piece, locale, slug, name
):
    piece = make_piece()
    config = get_solo()
    config.whatsapp_number = "573001234567"
    config.whatsapp_general_es = "Consulta ES {name} / {sku} / {url}"
    config.whatsapp_general_en = "Question EN {name} / {sku} / {url}"
    config.save()
    with override_settings(PUBLIC_SITE_URL="https://example.com"):
        data = client.get(URL + "/" + slug, {"locale": locale}).json()
    message = parse_qs(urlparse(data["whatsapp_url"]).query)["text"][0]
    prefix = "Consulta ES" if locale == "es" else "Question EN"
    segment = "piezas" if locale == "es" else "pieces"
    assert (
        message == f"{prefix} {name} / {piece.sku} / https://example.com/{locale}/{segment}/{slug}"
    )
    assert data["cta"] == {"kind": "add_to_cart"}
