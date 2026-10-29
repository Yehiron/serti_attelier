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
            models.Index(fields=["fulfillment_status"]),
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
    piece = models.ForeignKey("catalog.Piece", verbose_name=_("Pieza"), on_delete=models.PROTECT)
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
