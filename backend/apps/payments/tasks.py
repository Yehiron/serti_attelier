from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import PaymentAttempt
from .services import apply_transaction
from .wompi import WompiClient


@shared_task  # type: ignore[untyped-decorator]
def reconcile_pending() -> int:
    now = timezone.now()
    client = WompiClient()
    count = 0
    for attempt in PaymentAttempt.objects.filter(
        channel="wompi",
        status="PENDING",
        created_at__lt=now - timedelta(minutes=10),
        created_at__gt=now - timedelta(hours=48),
    ).iterator():
        tx = (
            client.get_transaction(attempt.provider_transaction_id)
            if attempt.provider_transaction_id
            else client.find_by_reference(attempt.reference)
        )
        if tx and tx.reference == attempt.reference:
            apply_transaction(tx, source="reconciliation")
            count += 1
    return count
