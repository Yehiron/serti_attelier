from __future__ import annotations

from typing import Any

from django.db import models
from django.db.models.functions import Upper
from django.utils.translation import gettext_lazy as _


class Coupon(models.Model):
    code = models.CharField(max_length=50)
    kind = models.CharField(
        max_length=7, choices=[("percent", _("Porcentaje")), ("fixed", _("Fijo"))]
    )
    value = models.PositiveBigIntegerField()
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    max_uses_per_email = models.PositiveIntegerField(null=True, blank=True)
    min_subtotal_cents = models.PositiveBigIntegerField(default=0)
    applies_to_sale_items = models.BooleanField(default=False)
    categories = models.ManyToManyField("catalog.Category", blank=True)
    collections = models.ManyToManyField("catalog.Collection", blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("cupón")
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
    coupon = models.ForeignKey(Coupon, on_delete=models.PROTECT)
    order = models.OneToOneField("orders.Order", on_delete=models.PROTECT)
    email_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.coupon_id}: {self.order_id}"
