from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import pytest
from django.db import close_old_connections, connection

from apps.orders.models import Order
from apps.payments.models import PaymentAttempt, PaymentEvent
from apps.payments.services import apply_transaction
from apps.promotions.models import Coupon, CouponRedemption

from .test_payments import tx_for


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_webhook_sync_concurrent_approval(order: Order) -> None:
    order.coupon = Coupon.objects.create(code="CONCURRENT", kind="percent", value=10)
    order.save(update_fields=["coupon"])
    tx = tx_for(order)
    barrier = Barrier(2)

    def apply(source: str) -> str:
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return apply_transaction(tx, source=source)
        finally:
            connection.close()

    with patch("apps.orders.events.order_paid") as hook, ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(apply, ["webhook", "sync"]))
    assert sorted(outcomes) == ["applied", "duplicate"]
    assert PaymentAttempt.objects.filter(order=order, status="APPROVED").count() == 1
    assert CouponRedemption.objects.filter(order=order).count() == 1
    assert PaymentEvent.objects.filter(outcome="applied").count() == 1
    hook.assert_called_once_with(order.pk)
