import json
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.core.observability import before_send, normalize_order_path
from apps.orders.api import OrderPublicThrottle
from apps.orders.models import Order, OrderStatusChange, public_token
from apps.orders.selectors import fulfillment_data

from .test_checkout import add, submit

pytestmark = pytest.mark.django_db


@pytest.fixture
def order(client, piece, payload):
    add(client, piece)
    assert submit(client, payload).status_code == 201
    return Order.objects.get()


@pytest.mark.parametrize(
    "state", ["unfulfilled", "preparing", "shipped", "delivered", "cancelled", "returned"]
)
def test_public_fulfillment(client, order, state):
    order.fulfillment_status = state
    order.carrier = "Transportadora"
    order.tracking_number = "123"
    order.tracking_url = "https://example.com/track/123"
    order.paid_at = timezone.now()
    order.payment_status = "approved"
    order.save()
    OrderStatusChange.objects.create(
        order=order,
        field="fulfillment_status",
        from_state="unfulfilled",
        to_state=state,
        note="SECRET INTERNAL REASON",
    )
    order.incidents.create(kind="no_piece", detail="SECRET INCIDENT")
    response = client.get(f"/api/v1/orders/{order.public_token}")
    assert response.status_code == 200
    data = response.data
    assert data["fulfillment"]["status"] == state
    assert data["fulfillment"]["carrier"] == "Transportadora"
    assert data["fulfillment"]["tracking_number"] == "123"
    assert data["fulfillment"]["tracking_url"] == order.tracking_url
    assert data["payment_review"] is True
    keys = (
        ["received", "paid", "cancelled"]
        if state == "cancelled"
        else ["received", "paid", "preparing", "shipped", "delivered"]
        + (["returned"] if state == "returned" else [])
    )
    assert [step["key"] for step in data["fulfillment"]["timeline"]] == keys
    assert all(set(step) == {"key", "label_key", "at"} for step in data["fulfillment"]["timeline"])
    encoded = json.dumps(data, default=str)
    assert "SECRET" not in encoded
    for private in [
        "customer_email",
        "customer_phone",
        "shipping_address_line",
        "incidents",
        "actor",
        "note",
    ]:
        assert private not in data
    assert response["Cache-Control"] == "no-store, private"
    assert response["Referrer-Policy"] == "no-referrer"
    if state == "shipped":
        assert data["fulfillment"]["shipped_at"] is not None
    if state == "delivered":
        assert data["fulfillment"]["delivered_at"] is not None


@pytest.mark.parametrize(
    "url", ["javascript:alert(1)", "ftp://example.com/x", "//example.com", "https://", ""]
)
def test_unsafe_tracking_url(order, url):
    order.tracking_url = url
    assert "tracking_url" not in fulfillment_data(order)


@pytest.mark.parametrize(
    "state,days,available",
    [
        ("delivered", 181, False),
        ("delivered", 179, True),
        ("cancelled", 181, False),
        ("returned", 181, False),
        ("expired", 31, False),
        ("expired", 29, True),
    ],
)
def test_tracking_expiry(client, order, state, days, available):
    at = timezone.now() - timedelta(days=days)
    if state == "expired":
        order.payment_status = "expired"
        order.reservation_expires_at = at
    else:
        order.payment_status = "approved"
        order.paid_at = at - timedelta(days=2)
        order.fulfillment_status = state
        if state == "delivered":
            order.delivered_at = at
        else:
            from unittest.mock import patch

            with patch("django.utils.timezone.now", return_value=at):
                OrderStatusChange.objects.create(
                    order=order, field="fulfillment_status", from_state="shipped", to_state=state
                )
    order.save()
    response = client.get(f"/api/v1/orders/{order.public_token}")
    assert response.status_code == (200 if available else 404)
    assert response["Cache-Control"] == "no-store, private"
    if not available:
        missing = client.get("/api/v1/orders/unknown")
        assert response.data["code"] == missing.data["code"]


def test_throttle(client, order, monkeypatch):
    monkeypatch.setattr(OrderPublicThrottle, "get_rate", lambda self: "1/min")
    cache.clear()
    path = f"/api/v1/orders/{order.public_token}"
    assert client.get(path).status_code == 200
    response = client.get(path)
    assert response.status_code == 429
    assert response["Cache-Control"] == "no-store, private"
    assert client.get(path, REMOTE_ADDR="192.0.2.5").status_code == 200


def test_tokens_and_logs():
    token = public_token()
    assert len(token) == 43  # 32 random bytes = 256 bits, base64url without padding.
    for path in [
        f"/api/v1/orders/{token}/payment-sync",
        f"https://serti.com/en/order/{token}?id=123",
        f"/es/pedido/{token}",
    ]:
        assert token not in normalize_order_path(path)
        assert ":token" in normalize_order_path(path)
        assert token not in json.dumps(
            before_send({"request": {"url": path}, "breadcrumbs": [{"message": path}]}, {})
        )


def test_sync_throttle_and_headers(client, order, monkeypatch):
    from apps.payments.api import SyncThrottle

    monkeypatch.setattr(SyncThrottle, "get_rate", lambda self: "1/min")
    path = f"/api/v1/orders/{order.public_token}/payment-sync"
    assert client.post(path, {}, format="json").status_code == 404
    response = client.post(path, {}, format="json")
    assert response.status_code == 429
    assert response["Cache-Control"] == "no-store, private"
    assert response["Referrer-Policy"] == "no-referrer"


def test_gunicorn_normalizes_atoms(monkeypatch):
    from gunicorn.glogging import Logger

    from apps.core.access_log import PrivateOrderLogger

    token = public_token()
    monkeypatch.setattr(
        Logger, "atoms", lambda *args: {"U": f"/api/v1/orders/{token}/payment-sync"}
    )
    logger = object.__new__(PrivateOrderLogger)
    assert logger.atoms(None, None, {}, None)["U"] == "/api/v1/orders/:token/payment-sync"
