from typing import Any

from django.contrib import admin
from django.http import HttpRequest
from django.utils.html import format_html_join
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(ModelAdmin):  # type: ignore[misc]  # Unfold has no stubs.
    list_display = ("at", "actor_repr", "action", "object_repr", "ip")
    list_filter = ("action", "at")
    search_fields = ("actor_repr", "object_repr")
    readonly_fields = tuple(field.name for field in AuditLog._meta.fields)

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.action.startswith("cms."):
            return tuple(
                "editorial_changes" if field == "diff" else field for field in self.readonly_fields
            )
        return self.readonly_fields

    def get_fields(self, request, obj=None):
        return self.get_readonly_fields(request, obj)

    @admin.display(description=_("Cambios"))
    def editorial_changes(self, obj):
        if not obj.diff:
            return "Sin cambios de campos registrados."
        return format_html_join(
            "",
            "<p><strong>{}</strong>: {} → {}</p>",
            (
                (label, values[0] or "Vacío", values[1] or "Vacío")
                for label, values in obj.diff.items()
            ),
        )

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return request.user.has_perm("audit.view_auditlog")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
