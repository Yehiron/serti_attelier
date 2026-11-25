from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import timedelta
from functools import partial
from typing import Any, cast

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
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
    "order_received": (("email", "customer"),),
    "payment_issue": (("email", "customer"),),
    "order_preparing": (("email", "customer"),),
    "order_delivered": (("email", "customer"),),
    "order_cancelled": (("email", "customer"), ("email", "serti")),
    "incident_resolved": (("email", "serti"),),
    "order_shipped": (("email", "customer"),),
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
def enqueue(
    order: Order,
    event: str,
    *,
    event_key: str = "",
    audience: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    if event not in EVENTS:
        raise ValueError("Unsupported notification event")
    count = 0
    for channel, target_audience in EVENT_TARGETS[event]:
        if audience is not None and audience != target_audience:
            continue
        target = target_audience
        locale = "en" if order.locale == "en" else "es"
        from django.template.loader import get_template

        if channel == "email":
            template = "internal" if target == "serti" else event
            for suffix in (".txt", ".html"):
                get_template(f"emails/{locale}/{template}{suffix}")
        delivery, created = NotificationDelivery.objects.get_or_create(
            idempotency_key=f"order:{order.pk}:{event}:{channel}:{target}"
            + (f":{event_key}" if event_key else ""),
            defaults={
                "order": order,
                "payload": {
                    "metadata": metadata or {},
                    "recipient_label": masked_recipient(
                        recipient_for(order, channel, target), channel
                    ),
                },
                "event": event,
                "channel": channel,
                "audience": target,
                "locale": locale,
                "template": "internal" if target == "serti" else event,
                "recipient_hash": email_digest(recipient_for(order, channel, target)),
                "next_attempt_at": timezone.now(),
            },
        )
        if created:
            count += 1
            transaction.on_commit(partial(dispatch, delivery.pk))
    return count


@transaction.atomic
def deliver(delivery_id: int) -> None:
    delivery = (
        NotificationDelivery.objects.select_for_update(of=("self",)).filter(pk=delivery_id).first()
    )
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
            delivery.payload["rendered"] = asdict(content)
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
            if order is not None:
                from .panel import publish

                publish(order, "exhausted", f"delivery:{delivery.pk}:exhausted")
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
            Q(next_attempt_at__lte=timezone.now()) | Q(next_attempt_at__isnull=True),
            status__in=["failed", "queued"],
        ).values_list("pk", flat=True)
    )
    for pk in ids:
        dispatch(pk)
    return len(ids)


@transaction.atomic
def resend(delivery_id: int, *, request: HttpRequest) -> bool:
    if not request.user.has_perm("notifications.resend_notificationdelivery"):
        raise PermissionDenied
    delivery = NotificationDelivery.objects.select_for_update(of=("self",)).get(pk=delivery_id)
    if not can_resend(delivery):
        return False
    previous = delivery.status
    previous_attempts = delivery.attempts
    if previous == "skipped":
        # Explicit, audited reconfiguration may bind a previously missing recipient.
        recipient = recipient_for(cast(Order, delivery.order), delivery.channel, delivery.audience)
        delivery.recipient_hash = email_digest(recipient)
        delivery.payload["recipient_label"] = masked_recipient(recipient, delivery.channel)
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
        diff={
            "status": [previous, "queued"],
            "attempts": [previous_attempts, 0],
            "reconfigured": [False, previous == "skipped"],
        },
    )
    transaction.on_commit(partial(dispatch, delivery.pk))
    return True


def masked_recipient(recipient: str, channel: str = "email") -> str:
    if not recipient:
        return "Sin configurar"
    if channel != "email":
        return "WhatsApp configurado"
    local, separator, domain = recipient.partition("@")
    return f"{local[:1]}***@{domain}" if separator else "Correo configurado"


RECONFIGURABLE = {
    "email_recipient_unconfigured",
    "email_smtp_unconfigured",
    "whatsapp_simulation",
    "whatsapp_provider_unconfigured",
    "whatsapp_unconfigured",
    "whatsapp_configuration_invalid",
}


def can_resend(delivery: NotificationDelivery) -> bool:
    if delivery.status in {"failed", "gave_up"}:
        return True
    if (
        delivery.status != "skipped"
        or delivery.last_error not in RECONFIGURABLE
        or not delivery.order_id
    ):
        return False
    if delivery.channel == "whatsapp":
        return not adapters.whatsapp_unavailable(delivery.event)
    return bool(
        recipient_for(cast(Order, delivery.order), delivery.channel, delivery.audience)
    ) and not (not settings.EMAIL_HOST and settings.EMAIL_BACKEND.endswith("smtp.EmailBackend"))


@transaction.atomic
def send_copy(delivery_id: int, *, request: HttpRequest) -> NotificationDelivery:
    if not request.user.has_perm("notifications.resend_notificationdelivery"):
        raise PermissionDenied
    # Serialize all copies for this order before reading the group count, including
    # copies of copies. Lock only self: order has nullable foreign keys.
    candidate = NotificationDelivery.objects.get(pk=delivery_id)
    if not candidate.order_id:
        raise ValidationError("El pedido ya no está disponible.")
    Order.objects.select_for_update(of=("self",)).get(pk=candidate.order_id)
    original = NotificationDelivery.objects.select_for_update(of=("self",)).get(pk=delivery_id)
    if original.status != "sent" or original.channel != "email" or original.audience != "customer":
        raise ValidationError(
            "Solo se pueden copiar correos al cliente aceptados por el proveedor."
        )
    root_key = original.idempotency_key.split(":copy:", 1)[0]
    count = NotificationDelivery.objects.filter(
        idempotency_key__startswith=root_key + ":copy:"
    ).count()
    if count >= 3:
        raise ValidationError("Este aviso ya tiene el máximo de 3 copias.")
    content = render_email(original, cast(Order, original.order))
    duplicate = NotificationDelivery.objects.create(
        order=original.order,
        event=original.event,
        channel="email",
        audience="customer",
        template=original.template,
        locale=original.locale,
        recipient_hash=original.recipient_hash,
        idempotency_key=f"{root_key}:copy:{count + 1}",
        payload={**original.payload, "rendered": asdict(content)},
        next_attempt_at=timezone.now(),
    )
    record(
        "notifications.copied",
        obj=duplicate,
        actor=request.user,
        request=request,
        diff={"source_delivery": [None, original.pk]},
    )
    transaction.on_commit(partial(dispatch, duplicate.pk))
    return duplicate
