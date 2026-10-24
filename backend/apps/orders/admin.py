from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline

from apps.core.exceptions import DomainError

from .models import Order, OrderItem, OrderStatusChange
from .services import transition_status


class ReadOnlyInline(TabularInline):  # type: ignore[misc]
    extra = 0
    can_delete = False

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


class ItemInline(ReadOnlyInline):
    model = OrderItem
    fields = ("sku", "name_es", "name_en", "piece_number", "unit_price_cents", "discount_cents")
    readonly_fields = fields


class HistoryInline(ReadOnlyInline):
    model = OrderStatusChange
    fields = ("field", "from_state", "to_state", "actor", "note", "at")
    readonly_fields = fields


@admin.register(Order)
class OrderAdmin(ModelAdmin):  # type: ignore[misc]
    list_display = (
        "number",
        "created_at",
        "customer_name",
        "total_cop",
        "payment_status",
        "fulfillment_status",
        "payment_channel",
        "wants_certificate",
    )
    list_filter = ("payment_status", "fulfillment_status", "payment_channel", "created_at")
    search_fields = ("number", "customer_email", "customer_phone")
    inlines = (ItemInline, HistoryInline)
    actions = ("prepare", "ship", "deliver", "cancel")
    readonly_fields = tuple(f.name for f in Order._meta.fields)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_fulfillment_permission(self, request: HttpRequest) -> bool:
        return request.user.has_perm("orders.change_fulfillment")

    @admin.display(description=_("Total COP"))
    def total_cop(self, obj: Order) -> str:
        return f"$ {obj.total_cents // 100:,}.{obj.total_cents % 100:02d}"

    def _move(self, request: HttpRequest, queryset: QuerySet[Order], target: str) -> None:
        for order in queryset:
            try:
                transition_status(order, "fulfillment_status", target, request=request)
            except DomainError:
                self.message_user(request, f"{order.number}: transición inválida.", messages.ERROR)

    @admin.action(description=_("Preparar"), permissions=["fulfillment"])
    def prepare(self, request: HttpRequest, queryset: QuerySet[Order]) -> None:
        self._move(request, queryset, "preparing")

    @admin.action(description=_("Marcar enviado"), permissions=["fulfillment"])
    def ship(self, request: HttpRequest, queryset: QuerySet[Order]) -> None:
        self._move(request, queryset, "shipped")

    @admin.action(description=_("Marcar entregado"), permissions=["fulfillment"])
    def deliver(self, request: HttpRequest, queryset: QuerySet[Order]) -> None:
        self._move(request, queryset, "delivered")

    @admin.action(description=_("Cancelar"), permissions=["fulfillment"])
    def cancel(self, request: HttpRequest, queryset: QuerySet[Order]) -> None:
        self._move(request, queryset, "cancelled")
