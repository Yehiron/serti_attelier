"""Persist domain notices inside the transaction; only dispatch runs after commit."""

import logging

from django.db import transaction

logger = logging.getLogger(__name__)


def _notify(order_id, event, *, event_key="", audience=None):
    try:
        from apps.notifications.services import enqueue

        from .models import Order

        # Savepoint: a broken template or insert must never roll back real money.
        with transaction.atomic():
            return enqueue(
                Order.objects.get(pk=order_id), event, event_key=event_key, audience=audience
            )
    except Exception as exc:
        logger.warning(
            "Notification persistence failed order=%s event=%s error=%s",
            order_id,
            event,
            type(exc).__name__,
        )
        try:
            from .incidents import open_incident
            from .models import Order, OrderIncident

            with transaction.atomic():
                open_incident(
                    Order.objects.get(pk=order_id),
                    OrderIncident.Kind.OTHER,
                    detail="No se pudo registrar un aviso. Revisa las notificaciones del pedido.",
                    blocking=False,
                    notify=False,
                )
        except Exception as incident_exc:
            logger.error(
                "Notification incident unavailable order=%s error=%s",
                order_id,
                type(incident_exc).__name__,
            )
        return 0


def order_paid(order_id):
    return _notify(order_id, "order_paid")


def manual_order_created(order_id):
    return _notify(order_id, "manual_payment_instructions")


def order_expired(order_id):
    return _notify(order_id, "reservation_expired")


def order_needs_attention(order_id):
    return _notify(order_id, "needs_attention")
