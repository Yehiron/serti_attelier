from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import Piece


class PieceReservation(models.Model):
    class Kind(models.TextChoices):
        ONLINE = "online", _("En línea")
        MANUAL = "manual", _("Manual")

    class Status(models.TextChoices):
        ACTIVE = "active", _("Activa")
        RELEASED = "released", _("Liberada")
        CONVERTED = "converted", _("Convertida")

    piece = models.ForeignKey(
        Piece,
        verbose_name=_("Pieza"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservations",
    )
    piece_sku = models.CharField(verbose_name=_("SKU de la pieza"), max_length=40, blank=True)
    piece_name_es = models.CharField(
        verbose_name=_("Nombre de la pieza"), max_length=250, blank=True
    )
    order = models.ForeignKey(
        "orders.Order",
        verbose_name=_("Pedido"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reservations",
    )
    kind = models.CharField(verbose_name=_("Tipo"), max_length=6, choices=Kind)
    status = models.CharField(
        verbose_name=_("Estado"), max_length=9, choices=Status, default=Status.ACTIVE
    )
    reference = models.CharField(verbose_name=_("Referencia"), max_length=64, blank=True)
    expires_at = models.DateTimeField(verbose_name=_("Vence el"))
    created_at = models.DateTimeField(verbose_name=_("Creado el"), auto_now_add=True)

    class Meta:
        verbose_name = _("reserva de pieza")
        verbose_name_plural = _("reservas de piezas")
        constraints = [
            models.UniqueConstraint(
                fields=["piece"],
                condition=models.Q(status="active"),
                name="one_active_reservation_per_piece",
            )
        ]
        indexes = [
            models.Index(fields=["status", "expires_at"]),
            models.Index(
                fields=["piece", "status", "expires_at"], name="reservation_piece_state_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.piece_sku or self.piece_id}: {self.status}"


class ImmutableStatusQuerySet(models.QuerySet["PieceStatusChange"]):
    def update(self, **kwargs: Any) -> int:
        raise ValueError("Status history is immutable")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValueError("Status history is immutable")


class PieceStatusChange(models.Model):
    class Reason(models.TextChoices):
        CHECKOUT = "checkout", _("Compra")
        PAYMENT_APPROVED = "payment_approved", _("Pago aprobado")
        MANUAL_PAYMENT_CONFIRMED = "manual_payment_confirmed", _("Pago manual confirmado")
        RESERVATION_EXPIRED = "reservation_expired", _("Reserva vencida")
        RELEASED = "released", _("Liberada")
        ADMIN = "admin", _("Administración")

    piece = models.ForeignKey(
        Piece,
        verbose_name=_("Pieza"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="status_changes",
    )
    piece_sku = models.CharField(verbose_name=_("SKU de la pieza"), max_length=40, blank=True)
    piece_name_es = models.CharField(
        verbose_name=_("Nombre de la pieza"), max_length=250, blank=True
    )
    from_state = models.CharField(
        verbose_name=_("Estado anterior"), max_length=12, choices=Piece.SaleState
    )
    to_state = models.CharField(
        verbose_name=_("Estado nuevo"), max_length=12, choices=Piece.SaleState
    )
    reason = models.CharField(verbose_name=_("Motivo"), max_length=30, choices=Reason)
    ref = models.CharField(verbose_name=_("Referencia"), max_length=64, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Responsable"),
        null=True,
        on_delete=models.SET_NULL,
    )
    at = models.DateTimeField(verbose_name=_("Fecha"), auto_now_add=True)
    objects = ImmutableStatusQuerySet.as_manager()

    class Meta:
        verbose_name = _("cambio de estado de pieza")
        verbose_name_plural = _("cambios de estado de piezas")
        ordering = ["-at"]

    def __str__(self) -> str:
        return f"{self.piece_sku or self.piece_id}: {self.from_state} → {self.to_state}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding or (self.pk and type(self).objects.filter(pk=self.pk).exists()):
            raise ValueError("Status history is immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValueError("Status history is immutable")
