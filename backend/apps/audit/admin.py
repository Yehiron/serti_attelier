from typing import Any

from django.contrib import admin
from django.http import HttpRequest
from django.utils.html import format_html_join
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from .models import AuditLog

ACTION_LABELS = {
    "cms.home_published": "Publicó la portada",
    "cms.page_published": "Publicó una página",
    "cms.menu_published": "Publicó el menú",
    "cms.brand_published": "Publicó la identidad de marca",
    "cms.draft_saved": "Guardó un borrador",
    "cms.home_restored": "Restauró la portada",
    "cms.page_restored": "Restauró una página",
    "orders.created": "Creó el pedido",
    "orders.cancelled": "Canceló el pedido",
    "orders.status_changed": "Cambió el estado del pedido",
    "orders.note_added": "Añadió una nota al pedido",
    "orders.exported": "Exportó el pedido",
    "payments.approved": "Aprobó el pago",
    "catalog.piece_created": "Creó la pieza",
    "catalog.piece_updated": "Actualizó la pieza",
    "catalog.piece_deleted": "Eliminó la pieza",
    "catalog.piece_published": "Publicó la pieza",
    "catalog.piece_archived": "Archivó la pieza",
    "catalog.photos_updated": "Actualizó las fotos",
    "catalog.relations_updated": "Actualizó las relaciones de la pieza",
    "catalog.collections_updated": "Actualizó las colecciones",
    "accounts.user_created": "Creó un usuario",
    "accounts.user_updated": "Actualizó un usuario",
    "accounts.user_deleted": "Eliminó un usuario",
    "accounts.access_changed": "Cambió permisos de acceso",
    "auth.login": "Inició sesión",
    "auth.logout": "Cerró sesión",
    "auth.login_failed": "Falló el inicio de sesión",
    "core.settings_updated": "Actualizó los datos del sitio",
    "inquiries.answered": "Marcó el mensaje como respondido",
    "inquiries.archived": "Archivó el mensaje",
    "inquiries.status_changed": "Cambió el estado del mensaje",
}


@admin.register(AuditLog)
class AuditLogAdmin(ModelAdmin):  # type: ignore[misc]  # Unfold has no stubs.
    list_display = ("at", "actor_repr", "action_label", "object_repr")
    list_filter = ("action", "at", "actor")
    search_fields = ("actor_repr", "object_repr", "action", "object_id")
    readonly_fields = tuple(field.name for field in AuditLog._meta.fields)

    @admin.display(description=_("Acción"), ordering="action")
    def action_label(self, obj):
        return ACTION_LABELS.get(obj.action, obj.action)

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
