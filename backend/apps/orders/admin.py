from __future__ import annotations

from typing import Any, cast

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import QuerySet
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import ChoicesDropdownFilter
from unfold.decorators import action, display
from unfold.utils import display_for_label

from apps.accounts.models import User
from apps.core.admin_presentation import thumbnail_url
from apps.core.exceptions import DomainError
from apps.core.formatting import format_admin_cop, format_bogota_date

from .card_admin import OrderCardAdminMixin
from .exports import export_orders
from .filters import OrderDateFilter, OrderTotalFilter
from .forms import FulfillmentForm
from .models import Order, OrderItem, OrderNote, OrderStatusChange
from .services import add_order_note, transition_status

# Printed for the customer, in the language of their order.
CERTIFICATE_TEXT = {
    "es": {
        "title": "Certificado",
        "title_em": "de autenticidad",
        "unique": "Pieza única · 1 de 1",
        "statement": (
            "SERTI certifica que la joya descrita en este documento es una pieza única, "
            "diseñada y hecha a mano en Colombia. No existe otra igual."
        ),
        "piece": "Pieza",
        "number": "Número de pieza",
        "stones": "Piedras",
        "materials": "Materiales",
        "owner": "Titular",
        "order": "Pedido",
        "issued": "Fecha de emisión",
        "code": "Código del certificado",
        "signature": "Firma y sello SERTI",
        "print": "Imprimir o guardar como PDF",
        "hint": "En la ventana de impresión elige «Guardar como PDF» para enviarlo por correo.",
        "back": "Volver al pedido",
    },
    "en": {
        "title": "Certificate",
        "title_em": "of authenticity",
        "unique": "One of a kind · 1 of 1",
        "statement": (
            "SERTI certifies that the jewel described in this document is a one-of-a-kind "
            "piece, designed and handmade in Colombia. There is no other like it."
        ),
        "piece": "Piece",
        "number": "Piece number",
        "stones": "Stones",
        "materials": "Materials",
        "owner": "Owner",
        "order": "Order",
        "issued": "Date of issue",
        "code": "Certificate code",
        "signature": "SERTI signature and seal",
        "print": "Print or save as PDF",
        "hint": "In the print dialog choose “Save as PDF” to send it by email.",
        "back": "Back to the order",
    },
}


def names(items: Any, locale: str) -> str:
    return ", ".join(getattr(item, f"name_{locale}") or item.name_es for item in items)


def certificate_available(order: Order) -> bool:
    return order.wants_certificate and order.payment_status == "approved"


class ReadOnlyInline(TabularInline):  # type: ignore[misc]
    extra = 0
    can_delete = False

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


class ItemInline(ReadOnlyInline):
    model = OrderItem
    fields = ("photo", "piece_link", "sku", "price", "discount")
    readonly_fields = fields

    verbose_name_plural = _("Lo que pidió")

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return request.user.has_perm("orders.view_order")

    @admin.display(description=_("Foto"))
    def photo(self, obj: OrderItem) -> str:
        image = obj.piece.images.filter(is_primary=True).first()
        return (
            format_html('<img src="{}" width="64" alt="">', thumbnail_url(image))
            if image and image.original
            else "—"
        )

    @admin.display(description=_("Pieza"))
    def piece_link(self, obj: OrderItem) -> str:
        return format_html(
            '<a href="{}">{}</a>',
            reverse("admin:catalog_piece_change", args=[obj.piece_id]),
            obj.name_es,
        )

    @admin.display(description=_("Precio"))
    def price(self, obj: OrderItem) -> str:
        return format_admin_cop(obj.unit_price_cents)

    @admin.display(description=_("Descuento"))
    def discount(self, obj: OrderItem) -> str:
        return format_admin_cop(obj.discount_cents)


class HistoryInline(ReadOnlyInline):
    verbose_name_plural = _("Historial")
    tab = True

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return request.user.has_perm("orders.view_order")

    model = OrderStatusChange
    fields = ("field_label", "previous_state", "next_state", "actor", "note", "at")
    readonly_fields = fields

    @admin.display(description=_("Cambio"))
    def field_label(self, obj: OrderStatusChange) -> str:
        return str(_("Pago") if obj.field == "payment_status" else _("Entrega"))

    def state_label(self, obj: OrderStatusChange, value: str) -> str:
        field = cast(Any, Order._meta.get_field(obj.field))
        return str(dict(field.flatchoices).get(value, value))

    @admin.display(description=_("Estado anterior"))
    def previous_state(self, obj: OrderStatusChange) -> str:
        return self.state_label(obj, obj.from_state)

    @admin.display(description=_("Estado nuevo"))
    def next_state(self, obj: OrderStatusChange) -> str:
        return self.state_label(obj, obj.to_state)


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
    verbose_name_plural = _("Notas")
    tab = True
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
class OrderAdmin(OrderCardAdminMixin, ModelAdmin):  # type: ignore[misc]
    list_display = (
        "number",
        "order_date",
        "client_name",
        "total_cop",
        "payment_badge",
        "fulfillment_badge",
        "certificate_requested",
        "attention_badge",
        "view_order",
    )
    change_list_template = "admin/orders/change_list.html"
    list_per_page = 20
    list_filter_submit = True
    list_display_links = ("number",)
    ordering = ("-created_at", "-pk")
    search_help_text = "Buscar por número, cliente, correo, teléfono o referencia"
    list_filter = (
        ("fulfillment_status", ChoicesDropdownFilter),
        ("payment_status", ChoicesDropdownFilter),
        ("created_at", OrderDateFilter),
        ("total_cents", OrderTotalFilter),
        "wants_certificate",
        "needs_attention",
        HasCouponFilter,
    )
    search_fields = ("number", "customer_name", "customer_email", "customer_phone", "items__sku")
    date_hierarchy = "created_at"
    inlines = (ItemInline, NoteInline, HistoryInline)
    actions = ("fulfillment", "export_csv", "confirm_manual", "print_certificate")
    actions_detail = (
        "detail_fulfillment",
        "detail_manual",
        "detail_certificate",
        "detail_whatsapp",
    )
    actions_row = ()
    readonly_fields = (
        "carrier",
        "tracking_number",
        "tracking_url",
        "number",
        "created_at",
        "customer_name",
        "email_link",
        "phone_link",
        "language",
        "shipping_address_line",
        "shipping_address_extra",
        "destination",
        "shipping_notes",
        "payment_channel",
        "payment_summary",
        "fulfillment_summary",
        "subtotal_cop",
        "discount_cop",
        "shipping_cop",
        "certificate_cop",
        "total_cop",
        "coupon",
        "certificate_link",
        "attention_badge",
    )
    fieldsets = (
        (
            _("Cliente"),
            {
                "fields": (
                    "number",
                    "created_at",
                    "customer_name",
                    "email_link",
                    "phone_link",
                    "language",
                    "attention_badge",
                ),
            },
        ),
        (
            _("Entrega"),
            {
                "fields": (
                    "shipping_address_line",
                    "shipping_address_extra",
                    "destination",
                    "shipping_notes",
                    "fulfillment_summary",
                    "carrier",
                    "tracking_number",
                    "tracking_url",
                ),
            },
        ),
        (
            _("Pago"),
            {
                "fields": (
                    "payment_channel",
                    "payment_summary",
                    "subtotal_cop",
                    "discount_cop",
                    "shipping_cop",
                    "certificate_cop",
                    "total_cop",
                    "coupon",
                    "certificate_link",
                ),
            },
        ),
    )

    def has_detail_fulfillment_permission(
        self, request: HttpRequest, object_id: Any = None
    ) -> bool:
        return self.has_fulfillment_permission(request) and bool(
            self.has_change_permission(request)
        )

    def has_detail_manual_permission(self, request: HttpRequest, object_id: Any = None) -> bool:
        order = self.get_object(request, str(object_id)) if object_id else None
        return bool(
            order
            and self.has_view_permission(request, order)
            and self.has_manual_permission(request)
            and order.payment_status == "awaiting_manual_payment"
        )

    def has_detail_certificate_permission(
        self, request: HttpRequest, object_id: Any = None
    ) -> bool:
        order = self.get_object(request, str(object_id)) if object_id else None
        return bool(
            order and self.has_view_permission(request, order) and certificate_available(order)
        )

    @action(description=_("Cambiar estado"), permissions=["detail_fulfillment"])  # type: ignore[untyped-decorator]
    def detail_fulfillment(self, request: HttpRequest, object_id: str) -> HttpResponse:
        order = self.get_object(request, object_id)
        if order is None:
            raise Http404
        if not self.has_change_permission(request, order):
            raise PermissionDenied
        response = self.fulfillment(request, Order.objects.filter(pk=order.pk))
        if isinstance(response, HttpResponseRedirect):
            self.message_user(request, _("Estado de entrega actualizado."), messages.SUCCESS)
            return HttpResponseRedirect(reverse("admin:orders_order_change", args=[object_id]))
        return response

    @action(description=_("Confirmar pago manual"), permissions=["detail_manual"])  # type: ignore[untyped-decorator]
    def detail_manual(self, request: HttpRequest, object_id: str) -> HttpResponse:
        return HttpResponseRedirect(reverse("admin:orders-confirm-manual", args=[object_id]))

    @action(
        description=_("Imprimir certificado"),
        permissions=["detail_certificate"],
        attrs={"target": "_blank", "rel": "noopener"},
    )  # type: ignore[untyped-decorator]
    def detail_certificate(self, request: HttpRequest, object_id: str) -> HttpResponse:
        return self.certificate_page(request, int(object_id))

    @action(
        description=_("Escribir por WhatsApp"),
        permissions=["view"],
        attrs={"target": "_blank", "rel": "noopener"},
    )  # type: ignore[untyped-decorator]
    def detail_whatsapp(self, request: HttpRequest, object_id: str) -> HttpResponse:
        order = self.get_object(request, object_id)
        if order is None:
            raise Http404
        if not self.has_view_permission(request, order):
            raise PermissionDenied
        return HttpResponseRedirect(self.whatsapp_url(order))

    def whatsapp_url(self, obj: Order) -> str:
        digits = "".join(c for c in obj.customer_phone if c.isdigit())
        if len(digits) == 10:
            digits = "57" + digits
        return f"https://wa.me/{digits}"

    @admin.display(description=_("Fecha"), ordering="created_at")
    def order_date(self, obj: Order) -> Any:
        from apps.core.formatting import BOGOTA

        local = timezone.localtime(obj.created_at, BOGOTA)
        return format_html(
            '<span style="white-space:nowrap">{}</span><br>'
            '<small style="white-space:nowrap;opacity:.7">{}</small>',
            local.strftime("%d/%m/%Y"),
            local.strftime("%I:%M %p").lstrip("0").lower(),
        )

    @admin.display(description=_("Cliente"), ordering="customer_name")
    def client_name(self, obj: Order) -> str:
        # Name and phone share one column so the row keeps room for "Ver pedido".
        return format_html(
            '{}<br><small style="white-space:nowrap;opacity:.7">{}</small>',
            obj.customer_name,
            obj.customer_phone,
        )

    @admin.display(description=_("Teléfono"))
    def client_phone(self, obj: Order) -> str:
        return obj.customer_phone

    @admin.display(description=_("Certificado"), boolean=True)
    def certificate_requested(self, obj: Order) -> bool:
        return obj.wants_certificate

    @admin.display(description=_("Pago"))
    def payment_summary(self, obj: Order) -> str:
        return cast(str, display_for_label(self.payment_badge(obj), "—", self.payment_badge.label))

    @admin.display(description=_("Estado"))
    def fulfillment_summary(self, obj: Order) -> str:
        return cast(
            str, display_for_label(self.fulfillment_badge(obj), "—", self.fulfillment_badge.label)
        )

    @admin.display(description=_("Correo"))
    def email_link(self, obj: Order) -> str:
        return format_html(
            '<a class="text-primary-600 underline" href="mailto:{}">{}</a>',
            obj.customer_email,
            obj.customer_email,
        )

    @admin.display(description=_("Teléfono / WhatsApp"))
    def phone_link(self, obj: Order) -> str:
        return format_html(
            '<a class="text-primary-600 underline" href="{}" target="_blank" rel="noopener">{}</a>',
            self.whatsapp_url(obj),
            obj.customer_phone,
        )

    @admin.display(description=_("Idioma"))
    def language(self, obj: Order) -> str:
        return str(_("Inglés") if obj.locale == "en" else _("Español"))

    @admin.display(description=_("Municipio y departamento"))
    def destination(self, obj: Order) -> str:
        return f"{obj.shipping_municipality.name}, {obj.shipping_municipality.department.name}"

    @display(  # type: ignore[untyped-decorator]
        description=_("Pago"),
        ordering="payment_status",
        label={
            "approved": "success",
            "pending": "warning",
            "awaiting_manual_payment": "warning",
            "declined": "danger",
            "error": "danger",
            "expired": "danger",
            "voided": "info",
        },
    )
    def payment_badge(self, obj: Order) -> tuple[str, str]:
        return obj.payment_status, obj.get_payment_status_display()

    @display(  # type: ignore[untyped-decorator]
        description=_("Estado"),
        ordering="fulfillment_status",
        label={
            "unfulfilled": "info",
            "preparing": "warning",
            "shipped": "info",
            "delivered": "success",
            "cancelled": "danger",
            "returned": "danger",
        },
    )
    def fulfillment_badge(self, obj: Order) -> tuple[str, str]:
        return obj.fulfillment_status, obj.get_fulfillment_status_display()

    @admin.display(description=_("Subtotal"))
    def subtotal_cop(self, obj: Order) -> str:
        return format_admin_cop(obj.subtotal_cents)

    @admin.display(description=_("Descuento"))
    def discount_cop(self, obj: Order) -> str:
        return format_admin_cop(obj.discount_cents)

    @admin.display(description=_("Envío"))
    def shipping_cop(self, obj: Order) -> str:
        return format_admin_cop(obj.shipping_cents)

    @admin.display(description=_("Certificado"))
    def certificate_cop(self, obj: Order) -> str:
        return format_admin_cop(obj.certificate_cents)

    def get_inlines(self, request: HttpRequest, obj: Any = None) -> tuple[Any, ...]:
        from apps.notifications.admin import DeliveryInline
        from apps.payments.admin import AttemptInline, OrderEventInline

        return (
            (*self.inlines, AttemptInline, OrderEventInline, DeliveryInline)
            if request.user.is_superuser
            else self.inlines
        )

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
                _("Este pedido requiere atención: revisa el pago y la disponibilidad."),
                messages.WARNING,
            )
        return cast(HttpResponse, super().change_view(request, object_id, form_url, extra_context))

    @admin.display(description="Pedido")
    def view_order(self, obj):
        return format_html(
            '<a class="oc-button" style="white-space:nowrap" data-order-card="{}" href="{}">'
            '<span class="material-symbols-outlined" aria-hidden="true">visibility</span>'
            " Ver pedido</a>",
            self.card_url(obj),
            reverse("admin:orders_order_change", args=[obj.pk]),
        )

    def get_urls(self) -> list[Any]:
        return [
            path(
                "<int:pk>/card/incidents/",
                self.admin_site.admin_view(self.card_incident),
                name="orders-card-incident",
            ),
            path(
                "<int:pk>/card/notes/",
                self.admin_site.admin_view(self.card_note),
                name="orders-card-note",
            ),
            path("<int:pk>/card/", self.admin_site.admin_view(self.card_page), name="orders-card"),
            path(
                "<int:pk>/card/status/",
                self.admin_site.admin_view(self.card_status),
                name="orders-card-status",
            ),
            path(
                "<int:pk>/certificate/",
                self.admin_site.admin_view(self.certificate_page),
                name="orders-certificate",
            ),
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

    @admin.display(description=_("Certificado de autenticidad"))
    def certificate_link(self, obj: Order) -> str:
        if not certificate_available(obj):
            return "—"
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">{}</a>',
            reverse("admin:orders-certificate", args=[obj.pk]),
            _("Abrir certificado para imprimir"),
        )

    @admin.action(description=_("Imprimir certificado de autenticidad"))
    def print_certificate(
        self, request: HttpRequest, queryset: QuerySet[Order]
    ) -> HttpResponse | None:
        if queryset.count() != 1:
            self.message_user(request, "Selecciona un solo pedido.", messages.ERROR)
            return None
        return HttpResponseRedirect(reverse("admin:orders-certificate", args=[queryset.get().pk]))

    def certificate_page(self, request: HttpRequest, pk: int) -> HttpResponse:
        order = (
            Order.objects.filter(pk=pk)
            .prefetch_related("items__piece__stones", "items__piece__materials")
            .first()
        )
        if order is None:
            raise Http404
        if not self.has_view_permission(request, order):
            raise PermissionDenied
        if not certificate_available(order):
            self.message_user(
                request,
                "El certificado solo se emite para pedidos que lo solicitaron y tienen el pago "
                "aprobado.",
                messages.ERROR,
            )
            return HttpResponseRedirect(reverse("admin:orders_order_change", args=[pk]))
        locale = "en" if order.locale == "en" else "es"
        issued = order.paid_at or order.created_at
        pieces = [
            {
                "name": item.name_en if locale == "en" else item.name_es,
                "number": item.piece_number or "",
                "sku": item.sku,
                "stones": names(item.piece.stones.all(), locale),
                "materials": names(item.piece.materials.all(), locale),
                "code": f"{order.number}-{item.sku}",
            }
            for item in order.items.all()
        ]
        return TemplateResponse(
            request,
            "admin/orders/certificate.html",
            {
                "order": order,
                "pieces": pieces,
                "locale": locale,
                "issued": format_bogota_date(issued, locale),
                "t": CERTIFICATE_TEXT[locale],
            },
        )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_fulfillment_permission(self, request: HttpRequest) -> bool:
        return request.user.has_perm("orders.change_fulfillment")

    @admin.display(description=_("Total"), ordering="total_cents")
    def total_cop(self, obj: Order) -> str:
        return format_admin_cop(obj.total_cents)

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

    @admin.action(description=_("Cambiar estado de entrega"), permissions=["fulfillment"])
    def fulfillment(self, request: HttpRequest, queryset: QuerySet[Order]) -> HttpResponse:
        if not self.has_fulfillment_permission(request) or not self.has_change_permission(request):
            raise PermissionDenied
        if any(not self.has_change_permission(request, order) for order in queryset):
            raise PermissionDenied
        form = FulfillmentForm(request.POST if "apply" in request.POST else None)
        if "apply" in request.POST and form.is_valid():
            updated, failures = 0, []
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
                        notify=form.cleaned_data["notify"],
                        expected_status=request.POST.get(f"expected_{order.pk}", ""),
                    )
                    updated += 1
                except (DomainError, ValidationError) as exc:
                    text = " ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
                    failures.append(f"{order.number} ({text})")
            summary = (
                "1 pedido actualizado." if updated == 1 else f"{updated} pedidos actualizados."
            )
            if failures:
                summary += (
                    " 1 no se pudo: "
                    if len(failures) == 1
                    else f" {len(failures)} no se pudieron: "
                ) + "; ".join(failures)
            self.message_user(request, summary, messages.WARNING if failures else messages.SUCCESS)
            return HttpResponseRedirect(request.get_full_path())
        return TemplateResponse(
            request,
            "admin/orders/fulfillment.html",
            {
                **self.admin_site.each_context(request),
                "form": form,
                "orders": queryset,
                "title": _("Cambiar estado de entrega"),
            },
        )

    def has_export_permission(self, request: HttpRequest) -> bool:
        return request.user.has_perm("orders.export_orders")

    @admin.action(description=_("Exportar CSV"), permissions=["export"])
    def export_csv(self, request: HttpRequest, queryset: QuerySet[Order]) -> HttpResponse:
        return export_orders(queryset, request=request)
