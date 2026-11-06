from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

EVENTS = (
    "incident_resolved",
    "order_preparing",
    "order_delivered",
    "order_cancelled",
    "order_shipped",
    "order_paid",
    "manual_payment_instructions",
    "reservation_expired",
    "needs_attention",
)
STATUSES = ("queued", "sent", "failed", "gave_up", "skipped")


class NotificationDelivery(models.Model):
    order = models.ForeignKey(
        "orders.Order",
        verbose_name=_("Pedido"),
        on_delete=models.PROTECT,
        null=True,
        related_name="deliveries",
    )
    event = models.CharField(
        verbose_name=_("Evento"), max_length=30, choices=[(s, s) for s in EVENTS]
    )
    channel = models.CharField(
        verbose_name=_("Canal"),
        max_length=8,
        choices=[("email", "email"), ("whatsapp", "whatsapp")],
    )
    audience = models.CharField(
        verbose_name=_("Destinatario"),
        max_length=8,
        choices=[("customer", "customer"), ("serti", "serti")],
    )
    template = models.CharField(verbose_name=_("Plantilla"), max_length=100)
    locale = models.CharField(verbose_name=_("Idioma"), max_length=2, default="es")
    recipient_hash = models.CharField(verbose_name=_("Huella del destinatario"), max_length=64)
    status = models.CharField(
        verbose_name=_("Estado"), max_length=8, default="queued", choices=[(s, s) for s in STATUSES]
    )
    attempts = models.PositiveSmallIntegerField(verbose_name=_("Intentos"), default=0)
    provider_message_id = models.CharField(
        verbose_name=_("Identificador del mensaje del proveedor"), max_length=200, blank=True
    )
    last_error = models.CharField(verbose_name=_("Último error"), max_length=100, blank=True)
    idempotency_key = models.CharField(
        verbose_name=_("Clave de idempotencia"), max_length=150, unique=True
    )
    created_at = models.DateTimeField(verbose_name=_("Creado el"), auto_now_add=True)
    sent_at = models.DateTimeField(verbose_name=_("Enviada el"), null=True, blank=True)
    next_attempt_at = models.DateTimeField(
        verbose_name=_("Próximo intento el"), null=True, blank=True
    )

    class Meta:
        verbose_name = _("entrega de notificación")
        verbose_name_plural = _("entregas de notificaciones")
        permissions = [("resend_notificationdelivery", "Puede reenviar notificaciones")]
        indexes = [models.Index(fields=["status", "next_attempt_at"])]

    def __str__(self) -> str:
        return f"{self.pk}: {self.event} / {self.channel} / {self.status}"
