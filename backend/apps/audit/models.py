from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _


class ImmutableQuerySet(models.QuerySet["AuditLog"]):
    def update(self, **kwargs: Any) -> int:
        raise ValueError("Audit records are immutable")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValueError("Audit records are immutable")


class AuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Responsable"),
        null=True,
        on_delete=models.SET_NULL,
    )
    actor_repr = models.CharField(
        verbose_name=_("Nombre del responsable"), max_length=150, blank=True
    )
    action = models.CharField(verbose_name=_("Acción"), max_length=80)
    content_type = models.ForeignKey(
        ContentType, verbose_name=_("Tipo de objeto"), null=True, on_delete=models.SET_NULL
    )
    object_id = models.CharField(  # noqa: DJ001 - nullable audit target
        verbose_name=_("Identificador del objeto"), max_length=255, null=True
    )
    object_repr = models.CharField(  # noqa: DJ001 - nullable audit target
        verbose_name=_("Descripción del objeto"), max_length=300, null=True
    )
    diff = models.JSONField(verbose_name=_("Cambios"), default=dict)
    ip = models.GenericIPAddressField(verbose_name=_("Dirección IP"), null=True)
    user_agent = models.CharField(verbose_name=_("Navegador"), max_length=300, blank=True)
    at = models.DateTimeField(verbose_name=_("Fecha"), auto_now_add=True, db_index=True)

    objects = ImmutableQuerySet.as_manager()

    class Meta:
        verbose_name = _("registro de auditoría")
        verbose_name_plural = _("registros de auditoría")
        ordering = ["-at"]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["-at"]),
            models.Index(fields=["action", "-at"], name="audit_action_at_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.action}: {self.actor_repr}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding or (
            self.pk is not None and type(self).objects.filter(pk=self.pk).exists()
        ):
            raise ValueError("Audit records are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValueError("Audit records are immutable")
