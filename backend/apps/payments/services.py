from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import timedelta
from typing import Any
from uuid import UUID

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import record
from apps.catalog.images import encode_webp, validated_image
from apps.inventory.services import PieceNotAvailable, convert_reservation, reserve_piece
from apps.orders import events
from apps.orders.exceptions import CheckoutError
from apps.orders.incidents import open_incident
from apps.orders.models import Order, OrderIncident
from apps.orders.services import transition_status
from apps.promotions.services import redeem_coupon

from .models import PaymentAttempt, PaymentEvent
from .wompi import WompiTransaction, checkout_fields, is_configured

logger = logging.getLogger(__name__)


def reservation_valid(order: Order) -> bool:
    return bool(order.reservation_expires_at and order.reservation_expires_at > timezone.now())


@transaction.atomic
def create_wompi_attempt(
    order: Order, *, key: UUID | None = None, retry: bool = False
) -> PaymentAttempt:
    order = Order.objects.select_for_update(of=("self",)).get(pk=order.pk)
    if order.fulfillment_status == "cancelled":
        raise CheckoutError(
            "payment_not_retryable",
            status=409,
            errors={"payment": ["El pedido está cancelado; no se puede iniciar otro pago."]},
        )
    if not is_configured():
        raise CheckoutError(
            "payment_unavailable",
            errors={"payment_channel": ["Wompi no está disponible: revisa su configuración."]},
        )
    if key:
        existing = PaymentAttempt.objects.filter(idempotency_key=key).first()
        if existing:
            if existing.order_id != order.pk:
                raise CheckoutError("idempotency_conflict", status=409)
            return existing
    last = order.payment_attempts.order_by("-sequence").first()
    if (
        order.payment_channel != "wompi"
        or order.payment_status != "pending"
        or not reservation_valid(order)
    ):
        raise CheckoutError("payment_not_retryable", status=409)
    if last and last.status in {"PENDING", "APPROVED"}:
        if not retry and last.status == "PENDING":
            return last
        raise CheckoutError("payment_not_retryable", status=409)
    sequence = last.sequence + 1 if last else 1
    return PaymentAttempt.objects.create(
        order=order,
        channel="wompi",
        sequence=sequence,
        reference=f"{order.number}-{sequence:02d}",
        amount_cents=order.total_cents,
        currency=order.currency,
        expires_at=order.reservation_expires_at,
        idempotency_key=key,
    )


def checkout_data(order: Order, *, include_customer: bool = False) -> dict[str, Any] | None:
    if (
        order.fulfillment_status == "cancelled"
        or order.payment_channel != "wompi"
        or order.payment_status != "pending"
        or not reservation_valid(order)
        or not is_configured()
    ):
        return None
    attempt = order.payment_attempts.order_by("-sequence").first()
    if not attempt or attempt.status != "PENDING":
        return None
    return {
        "checkout_url": settings.WOMPI_CHECKOUT_URL,
        "fields": checkout_fields(attempt, include_customer=include_customer),
    }


def payment_data(order: Order, *, include_customer: bool = False) -> dict[str, Any]:
    last = order.payment_attempts.order_by("-sequence").first()
    from .channels import channel_for

    return {
        "wompi": channel_for(order).checkout(order, include_customer=include_customer),
        "payment_unavailable": order.payment_channel == "wompi" and not is_configured(),
        "payment": {
            "status": last.status.lower()
            if last
            and last.status in {"DECLINED", "ERROR", "VOIDED"}
            and order.payment_status == "pending"
            else order.payment_status,
            "last_attempt": {
                "reference": last.reference,
                "status": last.status,
                "payment_method_type": last.payment_method_type,
            }
            if last
            else None,
            "can_retry": bool(
                order.fulfillment_status != "cancelled"
                and order.payment_channel == "wompi"
                and order.payment_status == "pending"
                and last
                and last.status in {"DECLINED", "ERROR", "VOIDED"}
                and reservation_valid(order)
            ),
        },
    }


def record_event(
    tx: WompiTransaction | None,
    *,
    outcome: str,
    source: str,
    checksum_valid: bool,
    provider_event: str = "transaction.updated",
    attempt: PaymentAttempt | None = None,
) -> PaymentEvent:
    return PaymentEvent.objects.create(
        attempt=attempt,
        order=attempt.order if attempt else None,
        provider_event=provider_event[:100],
        provider_transaction_id=tx.id if tx else "",
        status=tx.status if tx else "",
        payload=asdict(tx) if tx else {},
        checksum_valid=checksum_valid,
        outcome=outcome,
        source=source,
    )


def _sell(order: Order, *, manual: bool = False) -> None:
    reason = "manual_payment_confirmed" if manual else "payment_approved"
    for item in order.items.order_by("piece_id"):
        if item.piece_id is None:
            continue
        reservation = order.reservations.filter(
            piece_id=item.piece_id, status__in=["active", "converted"]
        ).first()
        if reservation and reservation.status == "converted":
            continue
        if reservation is None:
            reservation = reserve_piece(
                item.piece_id,
                kind="manual" if manual else "online",
                reference=order.number or "",
                expires_at=timezone.now() + timedelta(minutes=1),
            )
            reservation.order = order
            reservation.save(update_fields=["order"])
        convert_reservation(reservation.pk, reason=reason)


def _approve(
    attempt: PaymentAttempt,
    order: Order,
    *,
    actor: User | None = None,
    request: HttpRequest | None = None,
) -> None:
    if order.fulfillment_status == "cancelled":
        open_incident(order, OrderIncident.Kind.CANCELLED_PAYMENT)
    else:
        try:
            with transaction.atomic():
                _sell(order, manual=attempt.channel == "manual")
        except PieceNotAvailable:
            if attempt.channel == "manual":
                raise CheckoutError(
                    "piece_unavailable",
                    status=409,
                    errors={
                        "proof": [
                            "La pieza ya no está disponible; revisa el pago antes de confirmar."
                        ]
                    },
                ) from None
            open_incident(order, OrderIncident.Kind.NO_PIECE)
    transition_status(order, "payment_status", "approved", request=request)
    order.payment_status = "approved"
    order.paid_at = timezone.now()
    order.save(update_fields=["paid_at"])
    redeem_coupon(order)
    record("payments.approved", obj=order, actor=actor, request=request)
    events.order_paid(order.pk)


@transaction.atomic
def apply_transaction(
    tx: WompiTransaction,
    *,
    source: str,
    expected_reference: str | None = None,
    expected_id: str | None = None,
) -> str:
    """Solo para respuestas canónicas de Wompi; nunca para cuerpos de eventos."""
    if (expected_reference is not None and tx.reference != expected_reference) or (
        expected_id is not None and tx.id != expected_id
    ):
        record_event(tx, outcome="mismatch", source=source, checksum_valid=True)
        return "mismatch"
    # Lock the order before the attempt, serializing different attempts as well.
    candidate = PaymentAttempt.objects.filter(reference=tx.reference, channel="wompi").first()
    if candidate is None:
        logger.warning("Wompi: transacción canónica sin intento; origen=%s", source)
        record_event(tx, outcome="unknown_reference", source=source, checksum_valid=True)
        return "unknown_reference"
    order = Order.objects.select_for_update(of=("self",)).get(pk=candidate.order_id)
    attempt = PaymentAttempt.objects.select_for_update(of=("self",)).get(pk=candidate.pk)
    outcome = "applied"
    if (
        tx.amount_in_cents != attempt.amount_cents
        or tx.currency != "COP"
        or tx.currency != attempt.currency
        or (attempt.provider_transaction_id and attempt.provider_transaction_id != tx.id)
        or PaymentAttempt.objects.exclude(pk=attempt.pk)
        .filter(provider_transaction_id=tx.id)
        .exists()
    ):
        kind = (
            OrderIncident.Kind.AMOUNT_MISMATCH
            if tx.amount_in_cents != attempt.amount_cents
            or tx.currency != attempt.currency
            or tx.currency != "COP"
            else OrderIncident.Kind.SUSPICIOUS
        )
        open_incident(order, kind)
        record("payments.mismatch", obj=attempt)
        outcome = "mismatch"
    elif PaymentEvent.objects.filter(
        provider_transaction_id=tx.id, status=tx.status, outcome="applied"
    ).exists():
        outcome = "duplicate"
    elif tx.status == "APPROVED" and (
        order.payment_status in {"approved", "voided"} or attempt.status == "VOIDED"
    ):
        open_incident(order, OrderIncident.Kind.SUSPICIOUS)
        outcome = "mismatch"
    elif (tx.status not in {"APPROVED", "VOIDED"} and attempt.status != "PENDING") or (
        tx.status == "VOIDED" and attempt.status not in {"APPROVED", "PENDING"}
    ):
        outcome = "ignored_event"
    else:
        attempt.provider_transaction_id = tx.id
        attempt.payment_method_type = tx.payment_method_type
        attempt.status = tx.status
        attempt.save(
            update_fields=["provider_transaction_id", "payment_method_type", "status", "updated_at"]
        )
        if (
            tx.status == "PENDING"
            and order.payment_channel == "wompi"
            and order.payment_status == "pending"
            and order.fulfillment_status != "cancelled"
        ):
            events._notify(order.pk, "order_received")
        if tx.status == "APPROVED":
            _approve(attempt, order)
        elif tx.status == "VOIDED" and order.payment_status == "approved":
            transition_status(order, "payment_status", "voided")
            open_incident(
                order,
                OrderIncident.Kind.VOIDED_SHIPPED
                if order.fulfillment_status in {"shipped", "delivered", "returned"}
                else OrderIncident.Kind.SUSPICIOUS,
                detail="Pago anulado después de la aprobación.",
            )
        if tx.status != "APPROVED":
            record(f"payments.{tx.status.lower()}", obj=attempt)
    record_event(tx, outcome=outcome, source=source, checksum_valid=True, attempt=attempt)
    return outcome


@transaction.atomic
def confirm_manual_payment(
    order: Order, *, actor: User, reference: str, proof: UploadedFile[Any], request: HttpRequest
) -> PaymentAttempt:
    if not actor.has_perm("payments.confirm_manual_payment"):
        raise PermissionDenied
    order = Order.objects.select_for_update(of=("self",)).get(pk=order.pk)
    if order.fulfillment_status == "cancelled":
        raise CheckoutError(
            "payment_not_retryable",
            status=409,
            errors={"payment": ["El pedido está cancelado; no se puede confirmar el pago."]},
        )
    if order.payment_channel != "manual" or order.payment_status not in {
        "awaiting_manual_payment",
        "expired",
    }:
        raise CheckoutError("payment_not_retryable", status=409)
    if (
        not reference.strip()
        or len(reference) > 200
        or not proof
        or proof.size is None
        or proof.size > 10 * 1024 * 1024
    ):
        raise ValidationError("La referencia y un soporte de máximo 10 MB son obligatorios.")
    prefix = proof.read(5)
    proof.seek(0)
    if prefix != b"%PDF-":
        clean_proof = encode_webp(validated_image(proof))
        clean_proof.name = "proof.webp"
    else:
        clean_proof = ContentFile(proof.read(), name="proof.pdf")
    sequence = (
        order.payment_attempts.order_by("-sequence").values_list("sequence", flat=True).first() or 0
    ) + 1
    attempt = PaymentAttempt(
        order=order,
        channel="manual",
        sequence=sequence,
        reference=f"{order.number}-{sequence:02d}",
        amount_cents=order.total_cents,
        currency="COP",
        expires_at=order.reservation_expires_at,
        status="APPROVED",
        manual_reference=reference.strip(),
        manual_confirmed_by=actor,
        manual_confirmed_at=timezone.now(),
    )
    # Validate inventory before persisting a private file (storage is not transactional).
    _approve(attempt, order, actor=actor, request=request)
    attempt.manual_proof = clean_proof
    attempt.save()
    return attempt


def verify_received_event(receipt: PaymentEvent) -> bool:
    """False indica API no disponible. El recibo conserva solo campos permitidos."""
    from .wompi import WompiClient

    event_tx = WompiTransaction.parse(receipt.payload)
    if event_tx is None:
        return True
    try:
        canonical = WompiClient().get_transaction(event_tx.id)
    except (OSError, TimeoutError):
        canonical = None
    if canonical is None:
        return False
    if (
        canonical.id != event_tx.id
        or canonical.reference != event_tx.reference
        or canonical.amount_in_cents != event_tx.amount_in_cents
    ):
        record_event(event_tx, outcome="mismatch", source="webhook", checksum_valid=True)
        candidate = PaymentAttempt.objects.filter(
            reference=canonical.reference, channel="wompi"
        ).first()
        if candidate:
            open_incident(candidate.order, OrderIncident.Kind.SUSPICIOUS)
        logger.warning("Wompi: evento sospechoso; recibo=%s", receipt.pk)
        return True
    apply_transaction(canonical, source="webhook", expected_id=event_tx.id)
    return True
