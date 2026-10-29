from __future__ import annotations

from typing import Any

from django.db import models
from django.db.models.functions import Upper
from django.utils.translation import gettext_lazy as _


class Coupon(models.Model):
    code = models.CharField(verbose_name=_("Código"), max_length=50)
    kind = models.CharField(
        verbose_name=_("Tipo"),
        max_length=7,
        choices=[("percent", _("Porcentaje")), ("fixed", _("Fijo"))],
    )
    value = models.PositiveBigIntegerField(verbose_name=_("Valor"))
    starts_at = models.DateTimeField(verbose_name=_("Válido desde"), null=True, blank=True)
    ends_at = models.DateTimeField(verbose_name=_("Válido hasta"), null=True, blank=True)
    max_uses = models.PositiveIntegerField(verbose_name=_("Usos máximos"), null=True, blank=True)
    max_uses_per_email = models.PositiveIntegerField(
        verbose_name=_("Usos máximos por correo"), null=True, blank=True
    )
    min_subtotal_cents = models.PositiveBigIntegerField(
        verbose_name=_("Subtotal mínimo (centavos)"), default=0
    )
    applies_to_sale_items = models.BooleanField(
        verbose_name=_("Aplica a piezas en oferta"), default=False
    )
    categories = models.ManyToManyField(
        "catalog.Category", verbose_name=_("Categorías"), blank=True
    )
    collections = models.ManyToManyField(
        "catalog.Collection", verbose_name=_("Colecciones"), blank=True
    )
    is_active = models.BooleanField(verbose_name=_("Activo"), default=True)
    created_at = models.DateTimeField(verbose_name=_("Creado el"), auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name=_("Actualizado el"), auto_now=True)

    class Meta:
        verbose_name = _("cupón")
        verbose_name_plural = _("cupones")
        constraints = [
            models.UniqueConstraint(Upper("code"), name="coupon_upper_code_unique"),
            models.CheckConstraint(
                condition=models.Q(code=Upper("code")), name="coupon_code_upper"
            ),
            models.CheckConstraint(
                condition=models.Q(kind="percent", value__gte=1, value__lte=90)
                | models.Q(kind="fixed", value__gt=0),
                name="coupon_valid_value",
            ),
            models.CheckConstraint(
                condition=models.Q(starts_at__isnull=True)
                | models.Q(ends_at__isnull=True)
                | models.Q(ends_at__gt=models.F("starts_at")),
                name="coupon_valid_window",
            ),
            models.CheckConstraint(
                condition=models.Q(max_uses__isnull=True) | models.Q(max_uses__gt=0),
                name="coupon_positive_uses",
            ),
            models.CheckConstraint(
                condition=models.Q(max_uses_per_email__isnull=True)
                | models.Q(max_uses_per_email__gt=0),
                name="coupon_positive_email_uses",
            ),
        ]

    def __str__(self) -> str:
        return self.code

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)


class CouponRedemption(models.Model):
    coupon = models.ForeignKey(Coupon, verbose_name=_("Cupón"), on_delete=models.PROTECT)
    order = models.OneToOneField("orders.Order", verbose_name=_("Pedido"), on_delete=models.PROTECT)
    email_hash = models.CharField(verbose_name=_("Huella del correo"), max_length=64)
    created_at = models.DateTimeField(verbose_name=_("Creado el"), auto_now_add=True)

    class Meta:
        verbose_name = _("uso de cupón")
        verbose_name_plural = _("usos de cupones")

    def __str__(self) -> str:
        return f"{self.coupon_id}: {self.order_id}"
