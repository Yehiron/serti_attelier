from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.orders.models import ImmutableModel, ImmutableQuerySet

from .storage import private_storage, proof_path

STATUSES = [(s, s) for s in ("PENDING", "APPROVED", "DECLINED", "VOIDED", "ERROR")]


class PaymentAttempt(models.Model):
    order = models.ForeignKey(
        "orders.Order",
        verbose_name=_("Pedido"),
        on_delete=models.PROTECT,
        related_name="payment_attempts",
    )
    channel = models.CharField(
        verbose_name=_("Canal"), max_length=6, choices=[("wompi", "Wompi"), ("manual", "Manual")]
    )
    sequence = models.PositiveIntegerField(verbose_name=_("Secuencia"))
    reference = models.CharField(verbose_name=_("Referencia"), max_length=80, unique=True)
    idempotency_key = models.UUIDField(
        verbose_name=_("Clave de idempotencia"), null=True, unique=True
    )
    amount_cents = models.PositiveBigIntegerField(verbose_name=_("Importe (centavos)"))
    currency = models.CharField(verbose_name=_("Moneda"), max_length=3, default="COP")
    expires_at = models.DateTimeField(verbose_name=_("Vence el"), null=True)
    provider_transaction_id = models.CharField(
        verbose_name=_("Identificador de transacción del proveedor"),
        max_length=200,
        null=True,
        unique=True,
        blank=True,
    )
    payment_method_type = models.CharField(  # noqa: DJ001
        verbose_name=_("Tipo de medio de pago"), max_length=80, null=True, blank=True
    )
    status = models.CharField(
        verbose_name=_("Estado"), max_length=8, choices=STATUSES, default="PENDING"
    )
    manual_reference = models.CharField(
        verbose_name=_("Referencia del pago manual"), max_length=200, blank=True
    )
    manual_proof = models.FileField(
        verbose_name=_("Soporte del pago manual"),
        storage=private_storage,
        upload_to=proof_path,
        blank=True,
    )
    manual_confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Pago manual confirmado por"),
        null=True,
        on_delete=models.PROTECT,
    )
    manual_confirmed_at = models.DateTimeField(
        verbose_name=_("Pago manual confirmado el"), null=True
    )
    created_at = models.DateTimeField(verbose_name=_("Creado el"), auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name=_("Actualizado el"), auto_now=True)

    class Meta:
        verbose_name = _("intento de pago")
        verbose_name_plural = _("intentos de pago")
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
        "orders.Order",
        verbose_name=_("Pedido"),
        null=True,
        on_delete=models.PROTECT,
        related_name="payment_events",
    )
    attempt = models.ForeignKey(
        PaymentAttempt,
        verbose_name=_("Intento de pago"),
        null=True,
        on_delete=models.PROTECT,
        related_name="events",
    )
    provider_event = models.CharField(verbose_name=_("Evento del proveedor"), max_length=100)
    provider_transaction_id = models.CharField(
        verbose_name=_("Identificador de transacción del proveedor"), max_length=200, blank=True
    )
    status = models.CharField(verbose_name=_("Estado"), max_length=20, blank=True)
    payload = models.JSONField(verbose_name=_("Datos recibidos"), default=dict)
    checksum_valid = models.BooleanField(verbose_name=_("Firma válida"), default=False)
    outcome = models.CharField(
        verbose_name=_("Resultado"),
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
        verbose_name=_("Origen"),
        max_length=20,
        choices=[(s, s) for s in ("webhook", "sync", "reconciliation")],
    )
    received_at = models.DateTimeField(verbose_name=_("Recibido el"), auto_now_add=True)
    objects = ImmutableQuerySet["PaymentEvent"].as_manager()

    class Meta:
        verbose_name = _("evento de pago")
        verbose_name_plural = _("eventos de pago")
        constraints = [
            models.UniqueConstraint(
                fields=["provider_transaction_id", "status"],
                condition=models.Q(outcome="applied"),
                name="payment_event_applied_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.provider_transaction_id}: {self.outcome}"
