from __future__ import annotations

import secrets
from typing import Any, TypeVar

from django.conf import settings
from django.core.validators import MaxLengthValidator, URLValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


def public_token() -> str:
    return secrets.token_urlsafe(32)


class Order(models.Model):
    number = models.CharField(
        verbose_name=_("Número"), max_length=30, unique=True, null=True, blank=True, editable=False
    )
    public_token = models.CharField(
        verbose_name=_("Identificador de acceso público"),
        max_length=64,
        unique=True,
        default=public_token,
        editable=False,
    )
    idempotency_key = models.UUIDField(verbose_name=_("Clave de idempotencia"), unique=True)
    request_hash = models.CharField(verbose_name=_("Huella de la solicitud"), max_length=64)
    locale = models.CharField(verbose_name=_("Idioma"), max_length=2, default="es")
    customer_name = models.CharField(verbose_name=_("Nombre del cliente"), max_length=200)
    customer_email = models.EmailField(verbose_name=_("Correo del cliente"), db_index=True)
    customer_phone = models.CharField(verbose_name=_("Teléfono del cliente"), max_length=16)
    email_hash = models.CharField(verbose_name=_("Huella del correo"), max_length=64)
    shipping_address_line = models.CharField(verbose_name=_("Dirección de envío"), max_length=300)
    shipping_address_extra = models.CharField(
        verbose_name=_("Complemento de dirección"), max_length=300, blank=True
    )
    shipping_notes = models.TextField(verbose_name=_("Indicaciones de envío"), blank=True)
    shipping_municipality = models.ForeignKey(
        "core.Municipality", verbose_name=_("Municipio de envío"), on_delete=models.PROTECT
    )
    subtotal_cents = models.PositiveBigIntegerField(verbose_name=_("Subtotal (centavos)"))
    discount_cents = models.PositiveBigIntegerField(
        verbose_name=_("Descuento (centavos)"), default=0
    )
    shipping_cents = models.PositiveBigIntegerField(
        verbose_name=_("Costo de envío (centavos)"), default=0
    )
    certificate_cents = models.PositiveBigIntegerField(
        verbose_name=_("Costo del certificado (centavos)"), default=0
    )
    total_cents = models.PositiveBigIntegerField(verbose_name=_("Total (centavos)"))
    currency = models.CharField(verbose_name=_("Moneda"), max_length=3, default="COP")
    coupon = models.ForeignKey(
        "promotions.Coupon", verbose_name=_("Cupón"), null=True, on_delete=models.SET_NULL
    )
    payment_channel = models.CharField(
        verbose_name=_("Canal de pago"),
        max_length=6,
        choices=[("wompi", _("Wompi")), ("manual", _("Manual"))],
    )
    payment_status = models.CharField(
        verbose_name=_("Estado del pago"),
        max_length=25,
        default="pending",
        choices=[
            ("pending", _("Pendiente")),
            ("awaiting_manual_payment", _("Pendiente de pago manual")),
            ("approved", _("Aprobado")),
            ("declined", _("Rechazado")),
            ("error", _("Error")),
            ("expired", _("Vencido")),
            ("voided", _("Anulado")),
            ("cancelled", _("Anulado")),
        ],
    )
    fulfillment_status = models.CharField(
        verbose_name=_("Estado de preparación y envío"),
        max_length=12,
        default="unfulfilled",
        choices=[
            ("unfulfilled", _("Sin preparar")),
            ("preparing", _("En preparación")),
            ("shipped", _("Enviado")),
            ("delivered", _("Entregado")),
            ("cancelled", _("Cancelado")),
            ("returned", _("Devuelto")),
        ],
    )
    wants_certificate = models.BooleanField(verbose_name=_("Solicita certificado"), default=False)
    terms_version = models.PositiveIntegerField(verbose_name=_("Versión de términos"))
    privacy_version = models.PositiveIntegerField(verbose_name=_("Versión de privacidad"))
    privacy_consent_at = models.DateTimeField(verbose_name=_("Consentimiento de privacidad el"))
    needs_attention = models.BooleanField(verbose_name=_("Requiere atención"), default=False)
    carrier = models.CharField(_("Transportadora"), max_length=200, blank=True)
    tracking_number = models.CharField(_("Número de seguimiento"), max_length=200, blank=True)
    tracking_url = models.URLField(
        _("Enlace de seguimiento"), blank=True, validators=[URLValidator(schemes=["https"])]
    )
    shipped_at = models.DateTimeField(
        verbose_name=_("Enviado el"), null=True, blank=True, editable=False
    )
    delivered_at = models.DateTimeField(
        verbose_name=_("Entregado el"), null=True, blank=True, editable=False
    )
    paid_at = models.DateTimeField(verbose_name=_("Pagado el"), null=True, blank=True)
    reservation_expires_at = models.DateTimeField(verbose_name=_("Reserva válida hasta"), null=True)
    created_at = models.DateTimeField(verbose_name=_("Creado el"), auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name=_("Actualizado el"), auto_now=True)

    class Meta:
        verbose_name = _("pedido")
        verbose_name_plural = _("pedidos")
        permissions = [
            ("change_fulfillment", "Puede cambiar el estado operativo"),
            ("cancel_order", "Puede cancelar pedidos"),
            ("resolve_payment_incident", "Puede resolver incidencias de pago"),
            ("resolve_operational_incident", "Puede resolver incidencias operativas"),
            ("export_orders", "Puede exportar pedidos"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    total_cents=models.F("subtotal_cents")
                    - models.F("discount_cents")
                    + models.F("shipping_cents")
                    + models.F("certificate_cents")
                ),
                name="order_total_matches",
            ),
            models.CheckConstraint(
                condition=models.Q(total_cents__gt=0), name="order_total_positive"
            ),
        ]
        indexes = [
            models.Index(fields=["payment_status", "-created_at"]),
            models.Index(fields=["payment_status", "paid_at"], name="order_payment_paid_at_idx"),
            models.Index(fields=["fulfillment_status"]),
            models.Index(
                fields=["fulfillment_status", "-created_at"], name="order_fulfill_created_idx"
            ),
        ]

    def __str__(self) -> str:
        return self.number or str(self.pk)


T = TypeVar("T", bound=models.Model)


class ImmutableQuerySet(models.QuerySet[T]):
    def update(self, **kwargs: Any) -> int:
        raise ValueError("Order snapshots are immutable")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValueError("Order snapshots are immutable")


class ImmutableModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding or (
            self.pk is not None and type(self)._default_manager.filter(pk=self.pk).exists()
        ):
            raise ValueError("Order snapshots are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValueError("Order snapshots are immutable")


class OrderItem(ImmutableModel):
    order = models.ForeignKey(
        Order, verbose_name=_("Pedido"), on_delete=models.PROTECT, related_name="items"
    )
    piece = models.ForeignKey(
        "catalog.Piece", verbose_name=_("Pieza"), on_delete=models.SET_NULL, null=True, blank=True
    )
    sku = models.CharField(verbose_name=_("SKU"), max_length=40)
    piece_number = models.CharField(verbose_name=_("Número de pieza"), max_length=20, null=True)  # noqa: DJ001  # Snapshot API uses null.
    name_es = models.CharField(verbose_name=_("Nombre [es]"), max_length=250)
    name_en = models.CharField(verbose_name=_("Nombre [en]"), max_length=250)
    attributes = models.JSONField(verbose_name=_("Atributos"), default=dict)
    unit_price_cents = models.PositiveBigIntegerField(verbose_name=_("Precio unitario (centavos)"))
    discount_cents = models.PositiveBigIntegerField(
        verbose_name=_("Descuento (centavos)"), default=0
    )
    image_path = models.TextField(verbose_name=_("Ruta de imagen"), blank=True)
    image_snapshot = models.JSONField(verbose_name=_("Copia de imagen"), null=True)
    created_at = models.DateTimeField(verbose_name=_("Creado el"), auto_now_add=True)
    objects = ImmutableQuerySet["OrderItem"].as_manager()

    class Meta:
        verbose_name = _("pieza del pedido")
        verbose_name_plural = _("piezas del pedido")

    def __str__(self) -> str:
        return self.sku


class OrderStatusChange(ImmutableModel):
    order = models.ForeignKey(
        Order, verbose_name=_("Pedido"), on_delete=models.PROTECT, related_name="status_changes"
    )
    field = models.CharField(verbose_name=_("Campo"), max_length=20)
    from_state = models.CharField(verbose_name=_("Estado anterior"), max_length=25)
    to_state = models.CharField(verbose_name=_("Estado nuevo"), max_length=25)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Responsable"),
        null=True,
        on_delete=models.SET_NULL,
    )
    note = models.TextField(verbose_name=_("Nota"), blank=True)
    at = models.DateTimeField(verbose_name=_("Fecha"), auto_now_add=True)
    objects = ImmutableQuerySet["OrderStatusChange"].as_manager()

    class Meta:
        verbose_name = _("cambio de estado del pedido")
        verbose_name_plural = _("cambios de estado de pedidos")

    def __str__(self) -> str:
        return f"{self.order_id}: {self.to_state}"


class OrderNote(ImmutableModel):
    order = models.ForeignKey(
        Order, verbose_name=_("Pedido"), on_delete=models.PROTECT, related_name="notes"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("Autor"), on_delete=models.PROTECT
    )
    text = models.TextField(
        _("Nota interna"), max_length=2000, validators=[MaxLengthValidator(2000)]
    )
    created_at = models.DateTimeField(verbose_name=_("Creado el"), auto_now_add=True)
    objects = ImmutableQuerySet["OrderNote"].as_manager()

    class Meta:
        verbose_name = _("nota interna")
        verbose_name_plural = _("notas internas")
        ordering = ["created_at", "pk"]

    def __str__(self) -> str:
        return str(self.pk)


class OrderIncident(models.Model):
    class Kind(models.TextChoices):
        AMOUNT_MISMATCH = "amount_mismatch", _("Importe o moneda no coincide")
        NO_PIECE = "no_piece", _("Pago recibido sin pieza disponible")
        CANCELLED_PAYMENT = "cancelled_payment", _("Pago recibido en pedido cancelado")
        REFUND_PENDING = "refund_pending", _("Devolución de dinero pendiente")
        VOIDED_SHIPPED = "voided_shipped", _("Pago anulado tras el envío")
        SUSPICIOUS = "suspicious", _("Evento de pago sospechoso")
        OTHER = "other", _("Otra")

    order = models.ForeignKey(
        Order, on_delete=models.PROTECT, related_name="incidents", verbose_name=_("Pedido")
    )
    kind = models.CharField(_("Tipo"), max_length=30, choices=Kind)
    status = models.CharField(
        _("Estado"),
        max_length=8,
        choices=[("open", _("Abierta")), ("resolved", _("Resuelta"))],
        default="open",
    )
    blocking = models.BooleanField(_("Bloquea la preparación y el envío"), default=True)
    detail = models.TextField(_("Detalle"), blank=True, max_length=2000)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="order_incidents_created",
        verbose_name=_("Creada por"),
    )
    created_at = models.DateTimeField(_("Creada el"), auto_now_add=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="order_incidents_resolved",
        verbose_name=_("Resuelta por"),
    )
    resolved_at = models.DateTimeField(_("Resuelta el"), null=True)
    resolution_note = models.TextField(_("Nota de resolución"), blank=True, max_length=2000)

    class Meta:
        verbose_name = _("incidencia del pedido")
        verbose_name_plural = _("incidencias de pedidos")
        ordering = ["created_at", "pk"]
        indexes = [
            models.Index(
                fields=["kind"], condition=models.Q(status="open"), name="order_open_incident_idx"
            )
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["order", "kind"],
                condition=models.Q(status="open"),
                name="one_open_order_incident_kind",
            )
        ]

    def __str__(self):
        return f"{self.order_id}: {self.get_kind_display()}"

    @property
    def resolution_permission(self):
        return (
            "orders.resolve_operational_incident"
            if self.kind == self.Kind.OTHER
            else "orders.resolve_payment_incident"
        )
