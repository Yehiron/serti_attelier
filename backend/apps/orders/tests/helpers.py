from datetime import timedelta

from django.utils import timezone

from apps.inventory.services import convert_reservation, reserve_piece
from apps.orders.models import OrderItem


def sell_item_to_order(order, piece):
    """Build real inventory ownership for operational tests that start already paid."""
    if not order.items.filter(piece=piece).exists():
        OrderItem.objects.create(
            order=order,
            piece=piece,
            sku=piece.sku,
            name_es="Anillo",
            unit_price_cents=piece.price_cents,
        )
    reservation = order.reservations.filter(piece=piece, status="active").first()
    if not reservation:
        reservation = reserve_piece(
            piece.pk,
            kind="online",
            reference=order.number,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        reservation.order = order
        reservation.save(update_fields=["order"])
    convert_reservation(reservation.pk, reason="payment_approved")
