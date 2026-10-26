from __future__ import annotations

from typing import Any, cast

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import QuerySet
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline

from apps.accounts.models import User
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
    list_filter = (
        "payment_status",
        "fulfillment_status",
        "payment_channel",
        "created_at",
        "needs_attention",
    )
    search_fields = ("number", "customer_email", "customer_phone")
    inlines = (ItemInline, HistoryInline)
    actions = ("prepare", "ship", "deliver", "cancel", "confirm_manual")
    readonly_fields = tuple(f.name for f in Order._meta.fields)

    def get_inlines(self, request: HttpRequest, obj: Any = None) -> tuple[Any, ...]:
        from apps.payments.admin import AttemptInline, OrderEventInline

        return (*self.inlines, AttemptInline, OrderEventInline)

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        order = Order.objects.filter(pk=object_id).first()
        if order and order.needs_attention:
            self.message_user(
                request,
                "Este pedido requiere atención: revisa el pago y la disponibilidad.",
                messages.WARNING,
            )
        return cast(HttpResponse, super().change_view(request, object_id, form_url, extra_context))

    def get_urls(self) -> list[Any]:
        return [
            path(
                "<int:pk>/confirm-manual/",
                self.admin_site.admin_view(self.confirm_page),
                name="orders-confirm-manual",
            ),
            *super().get_urls(),
        ]

    def has_manual_permission(self, request: HttpRequest) -> bool:
        return request.user.has_perm("payments.confirm_manual_payment")

    @admin.action(description="Confirmar pago manual", permissions=["manual"])
    def confirm_manual(
        self, request: HttpRequest, queryset: QuerySet[Order]
    ) -> HttpResponse | None:
        if queryset.count() != 1:
            self.message_user(request, "Selecciona un solo pedido.", messages.ERROR)
            return None
        return HttpResponseRedirect(
            reverse("admin:orders-confirm-manual", args=[queryset.get().pk])
        )

    def confirm_page(self, request: HttpRequest, pk: int) -> HttpResponse:
        from apps.payments.forms import ManualPaymentForm
        from apps.payments.services import confirm_manual_payment

        if not self.has_manual_permission(request):
            raise PermissionDenied
        order = Order.objects.filter(pk=pk).first()
        if order is None:
            raise Http404
        form = ManualPaymentForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            try:
                confirm_manual_payment(
                    order,
                    actor=cast(User, request.user),
                    reference=form.cleaned_data["reference"],
                    proof=form.cleaned_data["proof"],
                    request=request,
                )
            except (DomainError, ValidationError) as exc:
                details = getattr(exc, "extra", {}).get("errors", {})
                if details:
                    for errors in details.values():
                        for error in errors:
                            form.add_error(None, error)
                else:
                    form.add_error(None, str(exc))
            else:
                return HttpResponseRedirect(reverse("admin:orders_order_change", args=[pk]))
        return TemplateResponse(
            request,
            "admin/payments/confirm.html",
            {**self.admin_site.each_context(request), "form": form, "order": order},
        )

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
