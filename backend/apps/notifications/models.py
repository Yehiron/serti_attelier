from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

EVENTS = (
    "order_received",
    "payment_issue",
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
EVENT_LABELS = {
    "order_received": "Pedido recibido · Pago en proceso",
    "payment_issue": "Pago en revisión",
    "order_paid": "Pago aprobado",
    "order_preparing": "En preparación",
    "order_shipped": "Pedido enviado",
    "order_delivered": "Pedido entregado",
    "order_cancelled": "Pedido cancelado",
    "manual_payment_instructions": "Instrucciones de pago",
    "reservation_expired": "Reserva vencida",
    "needs_attention": "Incidencia abierta",
    "incident_resolved": "Incidencia resuelta",
}
STATUS_LABELS = {
    "queued": "En cola",
    "sent": "Aceptado por el proveedor",
    "failed": "Fallido",
    "gave_up": "Intentos agotados",
    "skipped": "Omitido",
}


class NotificationDelivery(models.Model):
    order = models.ForeignKey(
        "orders.Order",
        verbose_name=_("Pedido"),
        on_delete=models.PROTECT,
        null=True,
        related_name="deliveries",
    )
    event = models.CharField(
        verbose_name=_("Evento"), max_length=30, choices=[(s, EVENT_LABELS[s]) for s in EVENTS]
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
        verbose_name=_("Estado"),
        max_length=8,
        default="queued",
        choices=list(STATUS_LABELS.items()),
    )
    attempts = models.PositiveSmallIntegerField(verbose_name=_("Intentos"), default=0)
    provider_message_id = models.CharField(
        verbose_name=_("Identificador del mensaje del proveedor"), max_length=200, blank=True
    )
    last_error = models.CharField(verbose_name=_("Último error"), max_length=100, blank=True)
    idempotency_key = models.CharField(
        verbose_name=_("Clave de idempotencia"), max_length=150, unique=True
    )
    payload = models.JSONField(_("Contenido y datos del aviso"), default=dict, blank=True)
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


class AdminNotification(models.Model):
    class Kind(models.TextChoices):
        PAID = "paid", _("Nuevo pedido pagado")
        MANUAL = "manual", _("Pago manual recibido")
        INCIDENT = "incident", _("Incidencia abierta")
        EXHAUSTED = "exhausted", _("Aviso fallido: intentos agotados")

    kind = models.CharField(_("Tipo de aviso"), max_length=12, choices=Kind)
    order = models.ForeignKey("orders.Order", verbose_name=_("Pedido"), on_delete=models.PROTECT)
    event_key = models.CharField(_("Identificador del evento"), max_length=150, unique=True)
    message = models.CharField(_("Mensaje"), max_length=200)
    payment_only = models.BooleanField(_("Solo responsables de pago"), default=False)
    created_at = models.DateTimeField(_("Creado el"), auto_now_add=True)

    class Meta:
        ordering = ["-pk"]
        verbose_name = _("aviso del panel")
        verbose_name_plural = _("avisos del panel")

    def __str__(self):
        return f"{self.pk}: {self.message}"


class AdminNotificationReceipt(models.Model):
    notification = models.ForeignKey(
        AdminNotification,
        verbose_name=_("Aviso"),
        on_delete=models.CASCADE,
        related_name="receipts",
    )
    user = models.ForeignKey("accounts.User", verbose_name=_("Usuario"), on_delete=models.CASCADE)
    read_at = models.DateTimeField(_("Leído el"), null=True, blank=True)

    class Meta:
        verbose_name = _("lectura de aviso")
        verbose_name_plural = _("lecturas de avisos")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "notification"], name="admin_notice_user_unique"
            )
        ]
        indexes = [models.Index(fields=["user", "read_at", "notification"])]

    def __str__(self):
        return f"{self.user_id}: {self.notification_id}"
