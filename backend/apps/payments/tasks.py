import logging
from datetime import timedelta
from typing import Any

from celery import shared_task
from django.conf import settings
from django.db.models import F, Q
from django.utils import timezone

from .models import PaymentAttempt, PaymentEvent
from .services import apply_transaction, verify_received_event
from .wompi import WompiClient

logger = logging.getLogger(__name__)
RETRY_DELAYS = (60, 300, 900, 3600)


@shared_task(bind=True, max_retries=4)  # type: ignore[untyped-decorator]
def verify_wompi_event(self: Any, receipt_id: int) -> None:
    receipt = PaymentEvent.objects.get(pk=receipt_id)
    if not verify_received_event(receipt):
        if self.request.retries >= len(RETRY_DELAYS):
            logger.warning("Wompi: verificación agotada; recibo=%s", receipt_id)
            return
        raise self.retry(countdown=RETRY_DELAYS[self.request.retries])


@shared_task  # type: ignore[untyped-decorator]
def reconcile_pending() -> int:
    now = timezone.now()
    pending = Q(
        status="PENDING",
        order__payment_status="pending",
        created_at__lt=now - timedelta(minutes=10),
    )
    approved = Q(
        status="APPROVED",
        updated_at__gte=now - timedelta(days=settings.WOMPI_RECONCILE_APPROVED_DAYS),
    )
    stale = Q(
        status="PENDING",
        created_at__lt=now - timedelta(days=settings.WOMPI_RECONCILE_PENDING_MAX_DAYS),
    )
    stale &= Q(provider_transaction_id__isnull=True) | Q(provider_transaction_id="")
    candidates = PaymentAttempt.objects.filter(channel="wompi").filter(pending | approved)
    stale_count = candidates.filter(stale).count()
    if stale_count:
        logger.warning("Wompi: pendientes antiguos sin ID omitidos; cantidad=%s", stale_count)
    attempts = candidates.exclude(stale).order_by(
        F("last_reconciled_at").asc(nulls_first=True), "pk"
    )[: max(0, settings.WOMPI_RECONCILE_BATCH)]
    client = WompiClient()
    count = 0
    for attempt in attempts:
        try:
            tx = (
                client.get_transaction(attempt.provider_transaction_id)
                if attempt.provider_transaction_id
                else client.find_by_reference(attempt.reference)
            )
        except (OSError, TimeoutError):
            tx = None
        PaymentAttempt.objects.filter(pk=attempt.pk).update(
            last_reconciled_at=timezone.now(),
            reconcile_failures=0 if tx else F("reconcile_failures") + 1,
        )
        if tx and tx.status == attempt.status and tx.id == attempt.provider_transaction_id:
            # Unchanged: avoid writing an audit row for every attempt on every beat run.
            continue
        if tx:
            apply_transaction(
                tx,
                source="reconciliation",
                expected_reference=attempt.reference,
                expected_id=attempt.provider_transaction_id,
            )
            count += 1
        elif attempt.reconcile_failures + 1 >= 5:
            logger.warning("Wompi: fallos de conciliación repetidos; intento=%s", attempt.pk)
    return count
