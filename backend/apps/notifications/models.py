from __future__ import annotations

from django.db import models

EVENTS = (
    "order_shipped",
    "order_paid",
    "manual_payment_instructions",
    "reservation_expired",
    "needs_attention",
)
STATUSES = ("queued", "sent", "failed", "gave_up", "skipped")


class NotificationDelivery(models.Model):
    order = models.ForeignKey(
        "orders.Order", on_delete=models.PROTECT, null=True, related_name="deliveries"
    )
    event = models.CharField(max_length=30, choices=[(s, s) for s in EVENTS])
    channel = models.CharField(max_length=8, choices=[("email", "email"), ("whatsapp", "whatsapp")])
    audience = models.CharField(
        max_length=8, choices=[("customer", "customer"), ("serti", "serti")]
    )
    template = models.CharField(max_length=100)
    locale = models.CharField(max_length=2, default="es")
    recipient_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=8, default="queued", choices=[(s, s) for s in STATUSES])
    attempts = models.PositiveSmallIntegerField(default=0)
    provider_message_id = models.CharField(max_length=200, blank=True)
    last_error = models.CharField(max_length=100, blank=True)
    idempotency_key = models.CharField(max_length=150, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        permissions = [("resend_notificationdelivery", "Puede reenviar notificaciones")]
        indexes = [models.Index(fields=["status", "next_attempt_at"])]
        verbose_name = "entrega de notificación"
        verbose_name_plural = "entregas de notificaciones"

    def __str__(self) -> str:
        return f"{self.pk}: {self.event} / {self.channel} / {self.status}"
