from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from unfold.admin import ModelAdmin

from apps.orders.admin import ReadOnlyInline

from .models import NotificationDelivery
from .services import resend


class DeliveryInline(ReadOnlyInline):
    model = NotificationDelivery
    fields = ("event", "channel", "audience", "status", "attempts", "last_error", "sent_at")
    readonly_fields = fields


@admin.register(NotificationDelivery)
class NotificationDeliveryAdmin(ModelAdmin):  # type: ignore[misc]
    list_display = ("order", "event", "channel", "audience", "status", "attempts", "created_at")
    list_filter = ("status", "channel", "audience", "event")
    search_fields = ("order__number",)
    readonly_fields = tuple(f.name for f in NotificationDelivery._meta.fields)
    actions = ("resend_failed",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_resend_permission(self, request: HttpRequest) -> bool:
        return request.user.has_perm("notifications.resend_notificationdelivery")

    @admin.action(description="Reenviar", permissions=["resend"])
    def resend_failed(self, request: HttpRequest, queryset: QuerySet[NotificationDelivery]) -> None:
        for pk in queryset.values_list("pk", flat=True):
            resend(pk, request=request)
