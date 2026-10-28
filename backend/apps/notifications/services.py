from __future__ import annotations

import logging
from datetime import timedelta
from functools import partial

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.audit.services import record
from apps.orders.models import Order
from apps.promotions.services import email_digest

from . import adapters
from .models import EVENTS, NotificationDelivery
from .rendering import render_email, whatsapp_parameters

logger = logging.getLogger(__name__)
BACKOFF_SECONDS = (60, 300, 900, 3600)
EVENT_TARGETS = {
    "order_paid": (("email", "customer"), ("email", "serti"), ("whatsapp", "serti")),
    "manual_payment_instructions": (("email", "customer"), ("email", "serti")),
    "reservation_expired": (("email", "customer"),),
    "needs_attention": (("email", "serti"), ("whatsapp", "serti")),
}


def recipient_for(order: Order, channel: str, audience: str) -> str:
    if audience == "customer":
        return order.customer_email.strip()
    return str(
        settings.SERTI_ORDERS_EMAIL if channel == "email" else settings.WHATSAPP_ORDERS_RECIPIENT
    ).strip()


def dispatch(delivery_id: int, countdown: int = 0) -> None:
    from .tasks import send_delivery

    try:
        if countdown:
            send_delivery.apply_async(args=[delivery_id], countdown=countdown)
        else:
            send_delivery.delay(delivery_id)
    except Exception:
        # Broker failures leave durable rows for the beat safety net. Never log exc_info.
        logger.warning("Notification dispatch unavailable delivery=%s", delivery_id)


@transaction.atomic
def enqueue(order: Order, event: str) -> int:
    if event not in EVENTS:
        raise ValueError("Unsupported notification event")
    count = 0
    for channel, audience in EVENT_TARGETS[event]:
        locale = order.locale if audience == "customer" and order.locale == "en" else "es"
        delivery, created = NotificationDelivery.objects.get_or_create(
            idempotency_key=f"order:{order.pk}:{event}:{channel}:{audience}",
            defaults={
                "order": order,
                "event": event,
                "channel": channel,
                "audience": audience,
                "locale": locale,
                "template": "internal" if audience == "serti" else event,
                "recipient_hash": email_digest(recipient_for(order, channel, audience)),
                "next_attempt_at": timezone.now(),
            },
        )
        if created:
            count += 1
            transaction.on_commit(partial(dispatch, delivery.pk))
    return count


@transaction.atomic
def deliver(delivery_id: int) -> None:
    delivery = NotificationDelivery.objects.select_for_update().filter(pk=delivery_id).first()
    if delivery is None or delivery.status in {"sent", "skipped", "gave_up"}:
        return
    now = timezone.now()
    if delivery.next_attempt_at and delivery.next_attempt_at > now:
        return
    order = delivery.order
    try:
        if order is None:
            raise adapters.ChannelSkipped("order_unavailable")
        recipient = recipient_for(order, delivery.channel, delivery.audience)
        if delivery.channel == "email":
            if not recipient:
                raise adapters.ChannelSkipped("email_recipient_unconfigured")
            if not settings.EMAIL_HOST and settings.EMAIL_BACKEND.endswith("smtp.EmailBackend"):
                raise adapters.ChannelSkipped("email_smtp_unconfigured")
        else:
            reason = adapters.whatsapp_unavailable(delivery.event)
            if reason:
                raise adapters.ChannelSkipped(reason)
        # Prevent configuration/address changes from silently redirecting a queued notice.
        if email_digest(recipient) != delivery.recipient_hash:
            raise adapters.ChannelSkipped("recipient_changed")
        if delivery.channel == "email":
            content = render_email(delivery, order)
            message_id = adapters.send_email(
                recipient, content.subject, content.text, content.html, content.reply_to
            )
        else:
            message_id = adapters.send_whatsapp(
                delivery.event, whatsapp_parameters(order, delivery.event), delivery.pk
            )
    except adapters.ChannelSkipped as exc:
        delivery.status = "skipped"
        delivery.last_error = str(exc)
        delivery.next_attempt_at = None
        logger.info("Notification skipped delivery=%s reason=%s", delivery.pk, delivery.last_error)
    except Exception as exc:
        # Exception bodies may contain SMTP addresses, Meta tokens or payloads: keep only the
        # exception type, which is enough to tell a bad password from a network outage.
        delivery.attempts += 1
        # Adapters raise fixed codes that already carry only the provider error type.
        error_type = str(exc) if isinstance(exc, adapters.ChannelFailure) else type(exc).__name__
        delivery.last_error = f"delivery_failed:{error_type}"[:120]
        logger.warning(
            "Notification failed delivery=%s attempt=%s error=%s",
            delivery.pk,
            delivery.attempts,
            error_type,
        )
        delivery.status = "gave_up" if delivery.attempts >= 5 else "failed"
        delivery.next_attempt_at = (
            now + timedelta(seconds=BACKOFF_SECONDS[delivery.attempts - 1])
            if delivery.status == "failed"
            else None
        )
        if delivery.status == "gave_up":
            logger.warning("Notification gave up delivery=%s attempts=5", delivery.pk)
        else:
            transaction.on_commit(
                partial(dispatch, delivery.pk, BACKOFF_SECONDS[delivery.attempts - 1])
            )
    else:
        delivery.attempts += 1
        delivery.status = "sent"
        delivery.provider_message_id = message_id
        delivery.sent_at = timezone.now()
        delivery.last_error = ""
        delivery.next_attempt_at = None
    delivery.save()


def retry_due() -> int:
    ids = list(
        NotificationDelivery.objects.filter(
            status__in=["failed", "queued"], next_attempt_at__lte=timezone.now()
        ).values_list("pk", flat=True)
    )
    for pk in ids:
        dispatch(pk)
    return len(ids)


@transaction.atomic
def resend(delivery_id: int, *, request: HttpRequest) -> bool:
    if not request.user.has_perm("notifications.resend_notificationdelivery"):
        raise PermissionDenied
    delivery = NotificationDelivery.objects.select_for_update().get(pk=delivery_id)
    if delivery.status not in {"failed", "gave_up"}:
        return False
    previous = delivery.status
    delivery.status = "queued"
    delivery.attempts = 0
    delivery.last_error = ""
    delivery.next_attempt_at = timezone.now()
    delivery.save()
    record(
        "notifications.resent",
        obj=delivery,
        actor=request.user,
        request=request,
        diff={"status": [previous, "queued"]},
    )
    transaction.on_commit(partial(dispatch, delivery.pk))
    return True
