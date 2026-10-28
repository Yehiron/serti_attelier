"""Post-commit domain hooks: notification failures never propagate to payments."""

import logging

logger = logging.getLogger(__name__)


def _notify(order_id: int, event: str) -> None:
    try:
        from apps.notifications.services import enqueue
        from apps.orders.models import Order

        enqueue(Order.objects.get(pk=order_id), event)
    except Exception as exc:
        logger.warning(
            "Notification hook failed order=%s event=%s error=%s",
            order_id,
            event,
            type(exc).__name__,
        )


def order_paid(order_id: int) -> None:
    _notify(order_id, "order_paid")


def manual_order_created(order_id: int) -> None:
    _notify(order_id, "manual_payment_instructions")


def order_expired(order_id: int) -> None:
    _notify(order_id, "reservation_expired")


def order_needs_attention(order_id: int) -> None:
    _notify(order_id, "needs_attention")
