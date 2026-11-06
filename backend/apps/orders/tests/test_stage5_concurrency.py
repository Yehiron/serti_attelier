from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.core.exceptions import ValidationError
from django.db import close_old_connections

from apps.accounts.models import User
from apps.accounts.roles import PROPIETARIO
from apps.core.tests.test_dashboard_client import staff
from apps.inventory.services import decide_cancelled_piece
from apps.notifications.models import AdminNotification, AdminNotificationReceipt
from apps.notifications.panel import publish
from apps.orders.models import Order
from apps.orders.tests.test_card import order as order_fixture
from apps.orders.tests.test_stage5 import held_piece

order = order_fixture
pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres]


def test_concurrent_same_panel_event_once(order):
    _, user = staff(PROPIETARIO)
    barrier = Barrier(2)

    def run():
        close_old_connections()
        try:
            local_order = Order.objects.get(pk=order.pk)
            barrier.wait(timeout=10)
            return publish(local_order, "paid", "concurrent:paid").pk
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: run(), range(2)))
    assert ids[0] == ids[1]
    assert AdminNotification.objects.count() == 1
    assert AdminNotificationReceipt.objects.filter(user=user).count() == 1


def test_concurrent_relist_only_one_change(order, piece):
    _, user = staff(PROPIETARIO)
    held_piece(order, piece, user)
    barrier = Barrier(2)

    def run():
        close_old_connections()
        try:
            actor = User.objects.get(pk=user.pk)
            barrier.wait(timeout=10)
            try:
                decide_cancelled_piece(piece.pk, actor=actor, order_id=order.pk, release=True)
                return "released"
            except ValidationError:
                return "changed"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert sorted(results) == ["changed", "released"]
    assert piece.status_changes.filter(from_state="reserved", to_state="available").count() == 1
