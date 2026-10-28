from __future__ import annotations

from typing import Any, cast

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import QuerySet
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline

from apps.accounts.models import User
from apps.core.exceptions import DomainError
from apps.core.formatting import format_cop

from .exports import export_orders
from .forms import FulfillmentForm
from .models import Order, OrderItem, OrderNote, OrderStatusChange
from .services import add_order_note, transition_status


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


class HasCouponFilter(admin.SimpleListFilter):
    title = _("Cupón")
    parameter_name = "has_coupon"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:
        return [("yes", str(_("Con cupón"))), ("no", str(_("Sin cupón")))]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Order]) -> QuerySet[Order]:
        if self.value() in {"yes", "no"}:
            return queryset.filter(coupon__isnull=self.value() == "no")
        return queryset


class NoteInline(TabularInline):  # type: ignore[misc]
    model = OrderNote
    extra = 0
    fields = ("text", "author", "created_at")
    readonly_fields = ("author", "created_at")
    can_delete = False

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return request.user.has_perm("orders.change_order") and request.user.has_perm(
            "orders.add_ordernote"
        )

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return request.user.has_perm("orders.view_ordernote")


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
        "attention_badge",
    )
    list_filter = (
        "payment_status",
        "fulfillment_status",
        "payment_channel",
        "created_at",
        "needs_attention",
        "wants_certificate",
        HasCouponFilter,
    )
    search_fields = ("number", "customer_name", "customer_email", "customer_phone", "items__sku")
    date_hierarchy = "created_at"
    inlines = (ItemInline, HistoryInline, NoteInline)
    actions = ("fulfillment", "export_csv", "confirm_manual")
    readonly_fields = tuple(f.name for f in Order._meta.fields)

    def get_inlines(self, request: HttpRequest, obj: Any = None) -> tuple[Any, ...]:
        from apps.notifications.admin import DeliveryInline
        from apps.payments.admin import AttemptInline, OrderEventInline

        return (*self.inlines, AttemptInline, OrderEventInline, DeliveryInline)

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
        return format_cop(obj.total_cents, "es")

    @admin.display(description=_("Requiere atención"), ordering="needs_attention")
    def attention_badge(self, obj: Order) -> str:
        if obj.needs_attention:
            return format_html(
                '<span class="bg-red-100 text-red-700 rounded px-2 py-1">{}</span>',
                _("Atención"),
            )
        return "—"

    def save_model(self, request: HttpRequest, obj: Order, form: Any, change: bool) -> None:
        # Order fields are immutable through this form; writes use domain services.
        return

    def save_formset(self, request: HttpRequest, form: Any, formset: Any, change: bool) -> None:
        instances = formset.save(commit=False)
        if formset.model is OrderNote:
            formset.new_objects = [
                add_order_note(form.instance, note.text, request=request) for note in instances
            ]

    @admin.action(description=_("Cambiar estado operativo"), permissions=["fulfillment"])
    def fulfillment(self, request: HttpRequest, queryset: QuerySet[Order]) -> HttpResponse:
        if not self.has_fulfillment_permission(request):
            raise PermissionDenied
        form = FulfillmentForm(request.POST if "apply" in request.POST else None)
        if "apply" in request.POST and form.is_valid():
            for order in queryset:
                try:
                    transition_status(
                        order,
                        "fulfillment_status",
                        form.cleaned_data["target"],
                        request=request,
                        note=form.cleaned_data["note"],
                        carrier=form.cleaned_data["carrier"],
                        tracking_number=form.cleaned_data["tracking_number"],
                        tracking_url=form.cleaned_data["tracking_url"],
                    )
                except (DomainError, ValidationError) as exc:
                    form.add_error(None, f"{order}: {exc}")
            if not form.errors:
                return HttpResponseRedirect(request.get_full_path())
        return TemplateResponse(
            request,
            "admin/orders/fulfillment.html",
            {
                **self.admin_site.each_context(request),
                "form": form,
                "orders": queryset,
                "title": _("Cambiar estado operativo"),
            },
        )

    def has_export_permission(self, request: HttpRequest) -> bool:
        return request.user.has_perm("orders.export_orders")

    @admin.action(description=_("Exportar CSV"), permissions=["export"])
    def export_csv(self, request: HttpRequest, queryset: QuerySet[Order]) -> HttpResponse:
        return export_orders(queryset, request=request)
