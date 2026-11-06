from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any
from uuid import uuid4

import pytest
from django.db import close_old_connections, connection
from django.test import RequestFactory

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Piece
from apps.core.selectors import get_solo
from apps.inventory.models import PieceReservation
from apps.orders.exceptions import CheckoutError
from apps.orders.models import Order
from apps.orders.services import create_order
from apps.promotions.models import Coupon

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres]


@pytest.mark.parametrize("limit", [False, True])
def test_concurrent_checkout(limit: bool, payload: dict[str, Any]) -> None:
    config = get_solo()
    if limit:
        Coupon.objects.create(code="ONCE", kind="percent", value=10, max_uses=1)
        payload["coupon_code"] = "ONCE"
    pieces = [
        Piece.objects.create(
            sku=f"CON-{n}",
            name_es=f"Pieza {n}",
            slug_es=f"con-{n}",
            price_cents=10000,
            status="published",
        )
        for n in range(2 if limit else 1)
    ]
    from datetime import timedelta

    from django.utils import timezone

    carts = [Cart.objects.create(expires_at=timezone.now() + timedelta(days=30)) for _ in range(2)]
    for n, cart in enumerate(carts):
        CartItem.objects.create(cart=cart, piece=pieces[n if limit else 0])
    barrier = Barrier(2)

    def attempt(pk: int) -> str:
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            cart = Cart.objects.get(pk=pk)
            create_order(cart, payload, idempotency_key=uuid4(), request=RequestFactory().post("/"))
            return "created"
        except CheckoutError as exc:
            return exc.default_code
        finally:
            # Each worker thread owns its DB connection; close it or the test DB can't be dropped.
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [c.pk for c in carts]))
    assert sorted(results) == sorted(["created", "coupon_exhausted" if limit else "piece_reserved"])
    assert Order.objects.count() == 1
    assert PieceReservation.objects.filter(status="active").count() == 1
    assert config.online_reservation_minutes > 0


def test_two_admins_one_status_winner(payload):
    from datetime import timedelta

    from django.core.exceptions import ValidationError
    from django.utils import timezone

    from apps.accounts.models import User
    from apps.core.models import Municipality
    from apps.inventory.services import convert_reservation, reserve_piece
    from apps.orders.models import OrderItem
    from apps.orders.services import transition_status

    user = User.objects.create_superuser(username="race-owner", password="test")
    order = Order.objects.create(
        number="SRT-RACE",
        idempotency_key=uuid4(),
        request_hash="x",
        customer_name="Cliente",
        customer_email="test@example.com",
        customer_phone="3001234567",
        email_hash="x",
        shipping_address_line="Calle",
        shipping_municipality=Municipality.objects.get(pk="05001"),
        subtotal_cents=10000,
        total_cents=10000,
        payment_channel="wompi",
        payment_status="approved",
        terms_version=1,
        privacy_version=1,
        privacy_consent_at=timezone.now(),
    )
    piece = Piece.objects.create(sku="RACE-STATUS", name_es="Anillo", price_cents=10000)
    OrderItem.objects.create(
        order=order, piece=piece, sku=piece.sku, name_es="Anillo", unit_price_cents=10000
    )
    reservation = reserve_piece(
        piece.pk,
        kind="online",
        reference=order.number,
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    reservation.order = order
    reservation.save()
    convert_reservation(reservation.pk, reason="payment_approved")
    barrier = Barrier(2)

    def change(_):
        close_old_connections()
        request = RequestFactory().post("/")
        request.user = User.objects.get(pk=user.pk)
        try:
            barrier.wait(timeout=10)
            transition_status(
                order,
                "fulfillment_status",
                "preparing",
                request=request,
                expected_status="unfulfilled",
                notify=False,
            )
            return "updated"
        except ValidationError as exc:
            return " ".join(exc.messages)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(change, range(2)))
    assert sorted(results) == sorted(["updated", "El pedido cambió, recarga."])
    assert order.status_changes.count() == 1
