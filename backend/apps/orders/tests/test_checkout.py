from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.catalog.models import Piece
from apps.core.selectors import get_solo
from apps.inventory.models import PieceReservation
from apps.inventory.tasks import release_expired_reservations
from apps.orders.models import Order
from apps.promotions.models import Coupon

pytestmark = pytest.mark.django_db


def add(client: APIClient, piece: Piece) -> Response:
    return client.post("/api/v1/cart/items", {"sku": piece.sku}, format="json")


def submit(client: APIClient, payload: dict[str, Any], key: str | None = None) -> Response:
    return client.post(
        "/api/v1/orders", payload, format="json", HTTP_IDEMPOTENCY_KEY=key or str(uuid4())
    )


@pytest.mark.parametrize("channel", ["manual", "wompi"])
def test_happy_path(
    client: APIClient,
    piece: Piece,
    payload: dict[str, Any],
    channel: str,
    django_capture_on_commit_callbacks: Any,
) -> None:
    payload["payment_channel"] = channel
    config = get_solo()
    config.online_reservation_minutes = 13
    config.manual_reservation_hours = 7
    config.certificate_price_cents = 200
    config.save()
    payload["wants_certificate"] = True
    response = add(client, piece)
    assert response.status_code == 201
    cookie = response.cookies["serti_cart"]
    assert cookie["httponly"] and cookie["secure"] and cookie["samesite"] == "Lax"
    key = str(uuid4())
    with django_capture_on_commit_callbacks(execute=True):
        response = submit(client, payload, key)
    assert response.status_code == 201, response.data
    order = Order.objects.get()
    assert order.customer_phone == "+573001234567" and order.total_cents == piece.price_cents + 200
    reservation = PieceReservation.objects.get()
    assert reservation.order == order and reservation.reference == order.number
    assert reservation.kind == ("online" if channel == "wompi" else "manual")
    duration = timedelta(minutes=13) if channel == "wompi" else timedelta(hours=7)
    assert abs((reservation.expires_at - order.created_at - duration).total_seconds()) < 2
    assert client.get("/api/v1/cart").data["count"] == 0
    replay = submit(client, payload, key)
    assert replay.status_code == 200 and replay.data == response.data
    payload["locale"] = "en"
    assert submit(client, payload, key).data["code"] == "idempotency_conflict"
    detail = client.get(f"/api/v1/orders/{order.public_token}")
    assert detail.status_code == 200
    for secret in ("test@example.com", "Calle 123", "3001234567"):
        assert secret not in str(detail.data)
    assert detail.data["items"][0]["name"] == "Anillo"
    assert AuditLog.objects.filter(action="orders.created").count() == 1


def test_errors_and_atomicity(client: APIClient, piece: Piece, payload: dict[str, Any]) -> None:
    assert submit(client, payload).data["code"] == "cart_empty"
    add(client, piece)
    payload["accepted_privacy_version"] = 1
    assert submit(client, payload).data["code"] == "consent_required"
    payload["accepted_privacy_version"] = 3
    payload["contact"]["email"] = "invalid"
    response = submit(client, payload)
    assert response.status_code == 422 and "errors" in response.data
    payload["contact"]["email"] = "test@example.com"
    other = Piece.objects.create(
        sku="P5-B", name_es="B", slug_es="p5-b", price_cents=100, status="published"
    )
    add(client, other)
    Piece.objects.filter(pk=other.pk).update(sale_state="reserved")
    response = submit(client, payload)
    assert response.status_code == 409 and response.data["skus"] == [other.sku]
    assert not Order.objects.exists() and not PieceReservation.objects.exists()
    piece.refresh_from_db()
    assert piece.sale_state == "available"


def test_coupon_validation_and_limits(
    client: APIClient, piece: Piece, payload: dict[str, Any]
) -> None:
    add(client, piece)
    payload["coupon_code"] = "unknown"
    response = client.post(
        "/api/v1/checkout/quote",
        {"coupon_code": "unknown", "wants_certificate": False},
        format="json",
    )
    assert response.status_code == 200 and response.data["coupon"]["reason"] == "coupon_invalid"
    assert submit(client, payload).data["code"] == "coupon_invalid"
    coupon = Coupon.objects.create(
        code="save", kind="percent", value=10, max_uses=1, max_uses_per_email=1
    )
    coupon.refresh_from_db()
    assert coupon.code == "SAVE"
    payload["coupon_code"] = "save"
    assert submit(client, payload).status_code == 201
    second = APIClient()
    other = Piece.objects.create(
        sku="P5-B", name_es="B", slug_es="p5-b", price_cents=100, status="published"
    )
    add(second, other)
    rejected = submit(second, payload)
    assert rejected.status_code == 422 and rejected.data["code"] == "coupon_exhausted"


def test_expiry(client: APIClient, piece: Piece, payload: dict[str, Any]) -> None:
    add(client, piece)
    assert submit(client, payload).status_code == 201
    past = timezone.now() - timedelta(seconds=1)
    PieceReservation.objects.update(expires_at=past)
    Order.objects.update(reservation_expires_at=past)
    assert release_expired_reservations() == 1
    order = Order.objects.get()
    piece.refresh_from_db()
    assert order.payment_status == "expired" and piece.sale_state == "available"
    assert order.status_changes.get().to_state == "expired"


def test_unknown_and_json_only(client: APIClient) -> None:
    assert client.get("/api/v1/orders/unknown").data["code"] == "order_not_found"
    assert client.post("/api/v1/cart/items", {"sku": "x"}).status_code == 415
    assert client.post("/api/v1/orders", {}, format="json").status_code == 422


@pytest.mark.parametrize(
    "status", ["pending", "awaiting_manual_payment", "approved", "declined", "expired", "error"]
)
def test_per_email_counting(
    client: APIClient, piece: Piece, payload: dict[str, Any], status: str
) -> None:
    Coupon.objects.create(code="EMAIL", kind="percent", value=10, max_uses_per_email=1)
    payload["coupon_code"] = "EMAIL"
    add(client, piece)
    assert submit(client, payload).status_code == 201
    Order.objects.update(payment_status=status)
    other = Piece.objects.create(
        sku="P5-B", name_es="B", slug_es="p5-b", price_cents=100, status="published"
    )
    second = APIClient()
    add(second, other)
    payload["contact"]["email"] = "TEST@example.com"
    response = submit(second, payload)
    if status in {"pending", "awaiting_manual_payment", "approved"}:
        assert response.status_code == 422 and response.data["code"] == "coupon_exhausted"
    else:
        assert response.status_code == 201


@pytest.mark.parametrize("configured", [False, True])
def test_detail_queries(
    client: APIClient,
    piece: Piece,
    payload: dict[str, Any],
    django_assert_max_num_queries: Any,
    configured: bool,
) -> None:
    add(client, piece)
    submit(client, payload)
    token = Order.objects.get().public_token
    # El checkout configurado consulta además el intento para construir sus campos.
    with (
        override_settings(WOMPI_PUBLIC_KEY="pub_test_fake" if configured else ""),
        django_assert_max_num_queries(4 if configured else 3),
    ):
        assert client.get(f"/api/v1/orders/{token}").status_code == 200


@pytest.mark.parametrize("state", ["sold", "preorder"])
def test_piece_conflicts(
    client: APIClient, piece: Piece, payload: dict[str, Any], state: str
) -> None:
    add(client, piece)
    Piece.objects.filter(pk=piece.pk).update(sale_state=state)
    response = submit(client, payload)
    assert response.status_code == 409 and response.data["skus"] == [piece.sku]
    assert not Order.objects.exists() and not PieceReservation.objects.exists()


def test_released_reservations_expire_before_deadline(
    client: APIClient, piece: Piece, payload: dict[str, Any]
) -> None:
    from apps.inventory.services import release_reservation
    from apps.orders.services import expire_stale_orders

    add(client, piece)
    assert submit(client, payload).status_code == 201
    release_reservation(PieceReservation.objects.get().pk, reason="released")
    assert expire_stale_orders() == 1
    assert Order.objects.get().payment_status == "expired"


def test_quote_checks_coupon_email_limit(client, piece, payload):
    Coupon.objects.create(code="EMAIL", kind="percent", value=10, max_uses_per_email=1)
    payload["coupon_code"] = "EMAIL"
    add(client, piece)
    assert submit(client, payload).status_code == 201
    second = APIClient()
    other = Piece.objects.create(
        sku="QUOTE-OTHER", name_es="Otra", slug_es="quote-other", price_cents=100,
        status="published",
    )
    add(second, other)
    data = {"coupon_code": "EMAIL", "wants_certificate": False}
    assert second.post("/api/v1/checkout/quote", data, format="json").data["coupon"]["applied"]
    data["email"] = payload["contact"]["email"].upper()
    coupon = second.post("/api/v1/checkout/quote", data, format="json").data["coupon"]
    assert coupon["applied"] is False and coupon["reason"] == "coupon_used_by_email"
    data["email"] = "other@example.com"
    assert second.post("/api/v1/checkout/quote", data, format="json").data["coupon"]["applied"]
