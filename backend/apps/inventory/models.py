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

    piece = models.ForeignKey(Piece, on_delete=models.PROTECT, related_name="reservations")
    order = models.ForeignKey(
        "orders.Order", null=True, blank=True, on_delete=models.PROTECT, related_name="reservations"
    )
    kind = models.CharField(max_length=6, choices=Kind)
    status = models.CharField(max_length=9, choices=Status, default=Status.ACTIVE)
    reference = models.CharField(max_length=64, blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["piece"],
                condition=models.Q(status="active"),
                name="one_active_reservation_per_piece",
            )
        ]
        indexes = [models.Index(fields=["status", "expires_at"])]
        verbose_name = _("reserva de pieza")

    def __str__(self) -> str:
        return f"{self.piece_id}: {self.status}"


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

    piece = models.ForeignKey(Piece, on_delete=models.PROTECT, related_name="status_changes")
    from_state = models.CharField(max_length=12, choices=Piece.SaleState)
    to_state = models.CharField(max_length=12, choices=Piece.SaleState)
    reason = models.CharField(max_length=30, choices=Reason)
    ref = models.CharField(max_length=64, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    at = models.DateTimeField(auto_now_add=True)
    objects = ImmutableStatusQuerySet.as_manager()

    class Meta:
        ordering = ["-at"]
        verbose_name = _("cambio de estado de pieza")

    def __str__(self) -> str:
        return f"{self.piece_id}: {self.from_state} → {self.to_state}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding or (self.pk and type(self).objects.filter(pk=self.pk).exists()):
            raise ValueError("Status history is immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValueError("Status history is immutable")
