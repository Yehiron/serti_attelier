from __future__ import annotations

from typing import Any

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import RequestFactory

from apps.accounts.models import User
from apps.accounts.roles import CONTENIDO, OPERACIONES, PROPIETARIO, ROLE_PERMISSIONS
from apps.orders.exceptions import CheckoutError
from apps.orders.models import Order, OrderItem
from apps.orders.services import transition_status
from apps.orders.transitions import FULFILLMENT_TRANSITIONS, PAYMENT_TRANSITIONS

from .test_checkout import add, submit

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("field", "table"),
    [("payment_status", PAYMENT_TRANSITIONS), ("fulfillment_status", FULFILLMENT_TRANSITIONS)],
)
def test_every_transition(
    field: str, table: dict[str, frozenset[str]], client: Any, piece: Any, payload: dict[str, Any]
) -> None:
    add(client, piece)
    assert submit(client, payload).status_code == 201
    order = Order.objects.get()
    request = RequestFactory().post("/")
    request.user = User.objects.create_superuser(
        username="owner", email="owner@example.com", password="test-password"
    )
    for source in table:
        for target in table:
            Order.objects.filter(pk=order.pk).update(**{field: source})
            if field == "fulfillment_status":
                order.incidents.update(status="resolved")
                from apps.catalog.models import Piece
                from apps.inventory.models import PieceReservation

                Piece.objects.filter(pk=piece.pk).update(sale_state="sold")
                PieceReservation.objects.filter(order=order).update(status="converted")
                Order.objects.filter(pk=order.pk).update(
                    payment_status="approved", carrier="Transportadora", shipped_at=None
                )
            if target in table[source]:
                transition_status(
                    order,
                    field,
                    target,
                    request=request,
                    note="Cambio revisado",
                    expected_status=source,
                )
                order.refresh_from_db()
                assert getattr(order, field) == target
            else:
                with pytest.raises((CheckoutError, ValidationError)):
                    transition_status(
                        order,
                        field,
                        target,
                        request=request,
                        note="Cambio revisado",
                        expected_status=source,
                    )


def test_permission_and_unpaid_preparing(client: Any, piece: Any, payload: dict[str, Any]) -> None:
    add(client, piece)
    submit(client, payload)
    order = Order.objects.get()
    with pytest.raises(PermissionDenied):
        transition_status(order, "fulfillment_status", "preparing")
    request = RequestFactory().post("/")
    request.user = User.objects.create_superuser(
        username="owner", email="owner@example.com", password="test-password"
    )
    with pytest.raises(ValidationError, match="pago no está aprobado"):
        transition_status(order, "fulfillment_status", "preparing", request=request)
    for role in (OPERACIONES, PROPIETARIO):
        assert "orders.change_fulfillment" in ROLE_PERMISSIONS[role]
        assert "promotions.change_coupon" in ROLE_PERMISSIONS[role]
    assert not any(p.startswith(("orders.", "promotions.")) for p in ROLE_PERMISSIONS[CONTENIDO])
    item = OrderItem.objects.get()
    with pytest.raises(ValueError):
        item.save()
    with pytest.raises(ValueError):
        OrderItem.objects.update(name_es="changed")
    with pytest.raises(ValueError):
        order.status_changes.all().delete()
