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
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_repr = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=80)
    content_type = models.ForeignKey(ContentType, null=True, on_delete=models.SET_NULL)
    object_id = models.CharField(max_length=255, null=True)  # noqa: DJ001 - nullable audit target
    object_repr = models.CharField(max_length=300, null=True)  # noqa: DJ001 - nullable audit target
    diff = models.JSONField(default=dict)
    ip = models.GenericIPAddressField(null=True)
    user_agent = models.CharField(max_length=300, blank=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = ImmutableQuerySet.as_manager()

    class Meta:
        verbose_name = _("registro de auditoría")
        verbose_name_plural = _("registros de auditoría")
        ordering = ["-at"]
        indexes = [models.Index(fields=["content_type", "object_id"]), models.Index(fields=["-at"])]

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
