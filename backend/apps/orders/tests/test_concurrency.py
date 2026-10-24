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
