from typing import Any

from django.contrib import admin
from django.http import HttpRequest
from unfold.admin import ModelAdmin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(ModelAdmin):  # type: ignore[misc]  # Unfold has no stubs.
    list_display = ("at", "actor_repr", "action", "object_repr", "ip")
    list_filter = ("action", "at")
    search_fields = ("actor_repr", "object_repr")
    readonly_fields = tuple(field.name for field in AuditLog._meta.fields)

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return request.user.has_perm("audit.view_auditlog")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
