from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.orders.models import ImmutableModel, ImmutableQuerySet

from .storage import private_storage, proof_path

STATUSES = [(s, s) for s in ("PENDING", "APPROVED", "DECLINED", "VOIDED", "ERROR")]


class PaymentAttempt(models.Model):
    order = models.ForeignKey(
        "orders.Order", on_delete=models.PROTECT, related_name="payment_attempts"
    )
    channel = models.CharField(max_length=6, choices=[("wompi", "Wompi"), ("manual", "Manual")])
    sequence = models.PositiveIntegerField()
    reference = models.CharField(max_length=80, unique=True)
    idempotency_key = models.UUIDField(null=True, unique=True)
    amount_cents = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3, default="COP")
    expires_at = models.DateTimeField(null=True)
    provider_transaction_id = models.CharField(max_length=200, null=True, unique=True, blank=True)
    payment_method_type = models.CharField(max_length=80, null=True, blank=True)  # noqa: DJ001
    status = models.CharField(max_length=8, choices=STATUSES, default="PENDING")
    manual_reference = models.CharField(max_length=200, blank=True)
    manual_proof = models.FileField(storage=private_storage, upload_to=proof_path, blank=True)
    manual_confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT
    )
    manual_confirmed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        permissions = [("confirm_manual_payment", "Puede confirmar pago manual")]
        constraints = [
            models.UniqueConstraint(fields=["order", "sequence"], name="payment_order_sequence"),
            models.UniqueConstraint(
                fields=["order"], condition=models.Q(status="APPROVED"), name="payment_one_approved"
            ),
        ]

    def __str__(self) -> str:
        return self.reference


class PaymentEvent(ImmutableModel):
    order = models.ForeignKey(
        "orders.Order", null=True, on_delete=models.PROTECT, related_name="payment_events"
    )
    attempt = models.ForeignKey(
        PaymentAttempt, null=True, on_delete=models.PROTECT, related_name="events"
    )
    provider_event = models.CharField(max_length=100)
    provider_transaction_id = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, blank=True)
    payload = models.JSONField(default=dict)
    checksum_valid = models.BooleanField(default=False)
    outcome = models.CharField(
        max_length=30,
        choices=[
            (s, s)
            for s in (
                "applied",
                "duplicate",
                "rejected_checksum",
                "mismatch",
                "unknown_reference",
                "ignored_event",
            )
        ],
    )
    source = models.CharField(
        max_length=20, choices=[(s, s) for s in ("webhook", "sync", "reconciliation")]
    )
    received_at = models.DateTimeField(auto_now_add=True)
    objects = ImmutableQuerySet["PaymentEvent"].as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider_transaction_id", "status"],
                condition=models.Q(outcome="applied"),
                name="payment_event_applied_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.provider_transaction_id}: {self.outcome}"
