from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.core.cache import cache
from django.test import RequestFactory, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.cart.models import Cart, CartItem
from apps.cart.services import delete_expired_carts, get_or_create_cart, set_cookie
from apps.catalog.models import Piece
from apps.orders.api import CartThrottle, OrderHourThrottle, OrderMinuteThrottle, QuoteThrottle

pytestmark = pytest.mark.django_db


def piece(n: int = 0, **kwargs: Any) -> Piece:
    return Piece.objects.create(
        sku=f"C-{n}",
        name_es=f"Pieza {n}",
        slug_es=f"c-{n}",
        price_cents=1000,
        status="published",
        **kwargs,
    )


def test_empty_tampered_cookie_and_remove() -> None:
    client = APIClient()
    assert client.get("/api/v1/cart").data["count"] == 0
    assert not Cart.objects.exists()
    client.cookies["serti_cart"] = "unsigned-or-tampered-token"
    assert client.get("/api/v1/cart").data["count"] == 0
    p = piece()
    assert client.post("/api/v1/cart/items", {"sku": p.sku}, format="json").status_code == 201
    assert client.post("/api/v1/cart/items", {"sku": p.sku}, format="json").data["count"] == 1
    assert client.delete(f"/api/v1/cart/items/{p.sku}").data["count"] == 0


@pytest.mark.parametrize("state", ["reserved", "sold", "preorder"])
def test_states(state: str) -> None:
    client = APIClient()
    p = piece(sale_state=state)
    response = client.post("/api/v1/cart/items", {"sku": p.sku}, format="json")
    if state == "reserved":
        assert response.status_code == 201 and not response.data["items"][0]["purchasable"]
        result = client.post("/api/v1/checkout/quote", {"wants_certificate": False}, format="json")
        assert result.data["items"] == []
    else:
        assert response.status_code == 409 and response.data["code"] == f"piece_{state}"


@pytest.mark.parametrize(
    ("state", "status", "reason"),
    [
        ("sold", "published", "sold"),
        ("preorder", "published", "preorder"),
        ("available", "hidden", "unavailable"),
        ("available", "draft", "unavailable"),
    ],
)
def test_clean_reports_removed(state: str, status: str, reason: str) -> None:
    client = APIClient()
    p = piece()
    client.post("/api/v1/cart/items", {"sku": p.sku}, format="json")
    Piece.objects.filter(pk=p.pk).update(sale_state=state, status=status)
    response = client.get("/api/v1/cart")
    assert response.data["removed"] == [{"sku": p.sku, "name": p.name, "reason": reason}]
    assert response.data["count"] == 0
    assert client.get("/api/v1/cart").data["removed"] == []


def test_cap_and_expiration() -> None:
    client = APIClient()
    for n in range(20):
        p = piece(n)
        assert client.post("/api/v1/cart/items", {"sku": p.sku}, format="json").status_code == 201
    p = piece(20)
    response = client.post("/api/v1/cart/items", {"sku": p.sku}, format="json")
    assert response.status_code == 422 and response.data["code"] == "cart_full"
    Cart.objects.update(expires_at=timezone.now() - timedelta(days=31))
    assert delete_expired_carts() > 0
    assert not Cart.objects.exists()


@pytest.mark.parametrize(
    ("path", "throttle"),
    [
        ("cart/items", CartThrottle),
        ("checkout/quote", QuoteThrottle),
        ("orders", OrderMinuteThrottle),
        ("orders", OrderHourThrottle),
    ],
)
def test_throttles(
    path: str, throttle: type[CartThrottle], monkeypatch: pytest.MonkeyPatch
) -> None:
    cache.clear()
    monkeypatch.setattr(throttle, "get_rate", lambda self: "1/min")
    client = APIClient()
    with override_settings(INTERNAL_API_TOKEN="internal"):
        client.post(
            f"/api/v1/{path}",
            {},
            format="json",
            HTTP_X_INTERNAL_TOKEN="internal",
            HTTP_X_FORWARDED_FOR="spoof, 192.0.2.8",
        )
        response = client.post(
            f"/api/v1/{path}",
            {},
            format="json",
            HTTP_X_INTERNAL_TOKEN="internal",
            HTTP_X_FORWARDED_FOR="different, 192.0.2.8",
        )
    assert response.status_code == 429 and response.data["code"] == "rate_limited"
    assert response["Content-Type"].startswith("application/problem+json")


def test_query_count_bounded(django_assert_max_num_queries: Any) -> None:
    client = APIClient()
    cart = get_or_create_cart(RequestFactory().get("/"))
    CartItem.objects.bulk_create([CartItem(cart=cart, piece=piece(n)) for n in range(20)])
    from rest_framework.response import Response

    response = Response()
    set_cookie(response, cart)
    client.cookies["serti_cart"] = response.cookies["serti_cart"].value
    with django_assert_max_num_queries(9):
        assert client.get("/api/v1/cart").data["count"] == 20


def test_subtotal_excludes_reserved_piece() -> None:
    client = APIClient()
    available = piece(1)
    reserved = piece(2, sale_state="reserved")
    client.post("/api/v1/cart/items", {"sku": available.sku}, format="json")
    response = client.post("/api/v1/cart/items", {"sku": reserved.sku}, format="json")
    assert response.data["count"] == 2
    assert response.data["subtotal"]["amount_cents"] == 1000
