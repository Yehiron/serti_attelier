from __future__ import annotations

import secrets
from typing import Any, TypeVar

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


def public_token() -> str:
    return secrets.token_urlsafe(32)


class Order(models.Model):
    number = models.CharField(max_length=30, unique=True, null=True, blank=True, editable=False)
    public_token = models.CharField(
        max_length=64, unique=True, default=public_token, editable=False
    )
    idempotency_key = models.UUIDField(unique=True)
    request_hash = models.CharField(max_length=64)
    locale = models.CharField(max_length=2, default="es")
    customer_name = models.CharField(max_length=200)
    customer_email = models.EmailField(db_index=True)
    customer_phone = models.CharField(max_length=16)
    email_hash = models.CharField(max_length=64)
    shipping_address_line = models.CharField(max_length=300)
    shipping_address_extra = models.CharField(max_length=300, blank=True)
    shipping_notes = models.TextField(blank=True)
    shipping_municipality = models.ForeignKey("core.Municipality", on_delete=models.PROTECT)
    subtotal_cents = models.PositiveBigIntegerField()
    discount_cents = models.PositiveBigIntegerField(default=0)
    shipping_cents = models.PositiveBigIntegerField(default=0)
    certificate_cents = models.PositiveBigIntegerField(default=0)
    total_cents = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3, default="COP")
    coupon = models.ForeignKey("promotions.Coupon", null=True, on_delete=models.SET_NULL)
    payment_channel = models.CharField(
        max_length=6, choices=[("wompi", _("Wompi")), ("manual", _("Manual"))]
    )
    payment_status = models.CharField(
        max_length=25,
        default="pending",
        choices=[
            (s, s)
            for s in (
                "pending",
                "awaiting_manual_payment",
                "approved",
                "declined",
                "error",
                "expired",
                "voided",
            )
        ],
    )
    fulfillment_status = models.CharField(
        max_length=12,
        default="unfulfilled",
        choices=[
            (s, s)
            for s in ("unfulfilled", "preparing", "shipped", "delivered", "cancelled", "returned")
        ],
    )
    wants_certificate = models.BooleanField(default=False)
    terms_version = models.PositiveIntegerField()
    privacy_version = models.PositiveIntegerField()
    privacy_consent_at = models.DateTimeField()
    needs_attention = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)
    reservation_expires_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("pedido")
        permissions = [("change_fulfillment", "Puede cambiar el estado operativo")]
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
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="items")
    piece = models.ForeignKey("catalog.Piece", on_delete=models.PROTECT)
    sku = models.CharField(max_length=40)
    piece_number = models.CharField(max_length=20, null=True)  # noqa: DJ001  # Snapshot API uses null.
    name_es = models.CharField(max_length=250)
    name_en = models.CharField(max_length=250)
    attributes = models.JSONField(default=dict)
    unit_price_cents = models.PositiveBigIntegerField()
    discount_cents = models.PositiveBigIntegerField(default=0)
    image_path = models.TextField(blank=True)
    image_snapshot = models.JSONField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = ImmutableQuerySet["OrderItem"].as_manager()

    def __str__(self) -> str:
        return self.sku


class OrderStatusChange(ImmutableModel):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="status_changes")
    field = models.CharField(max_length=20)
    from_state = models.CharField(max_length=25)
    to_state = models.CharField(max_length=25)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    note = models.TextField(blank=True)
    at = models.DateTimeField(auto_now_add=True)
    objects = ImmutableQuerySet["OrderStatusChange"].as_manager()

    def __str__(self) -> str:
        return f"{self.order_id}: {self.to_state}"
