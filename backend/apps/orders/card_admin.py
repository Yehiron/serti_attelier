"""Admin order card: server rendering is shared by the drawer, page and print view."""

from copy import copy

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Prefetch
from django.http import Http404, HttpResponseNotAllowed
from django.template.response import TemplateResponse
from django.urls import reverse

from apps.core.exceptions import DomainError
from apps.core.formatting import format_admin_cop, format_bogota_datetime

from .forms import CardFulfillmentForm
from .models import Order, OrderStatusChange
from .services import add_order_note, transition_status
from .transitions import FULFILLMENT_TRANSITIONS


class OrderCardAdminMixin:
    @staticmethod
    def card_url(order):
        return reverse("admin:orders-card", args=[order.pk])

    def card_order(self, request, pk):
        # Check model permission before revealing whether an order exists.
        if not self.has_view_permission(request):
            raise PermissionDenied
        order = (
            self.get_queryset(request)
            .select_related("shipping_municipality__department", "coupon")
            .prefetch_related(
                "items__piece__images",
                "notes__author",
                Prefetch(
                    "status_changes",
                    queryset=OrderStatusChange.objects.select_related("actor").order_by("at", "pk"),
                ),
            )
            .filter(pk=pk)
            .first()
        )
        if order is None:
            raise Http404
        if not self.has_view_permission(request, order):
            raise PermissionDenied
        return order

    def card_context(self, request, order, **extra):
        from .admin import certificate_available

        history = []
        for change in order.status_changes.all():
            labels = dict(Order._meta.get_field(change.field).flatchoices)
            history.append(
                {
                    "date": format_bogota_datetime(change.at, "es"),
                    "field": "Pago" if change.field == "payment_status" else "Entrega",
                    "previous": labels.get(change.from_state, change.from_state),
                    "next": labels.get(change.to_state, change.to_state),
                    "actor": change.actor or "Sistema",
                    "note": change.note,
                }
            )
        allowed = FULFILLMENT_TRANSITIONS.get(order.fulfillment_status, ())
        return {
            **self.admin_site.each_context(request),
            "title": f"Pedido {order.number}",
            "opts": self.model._meta,
            "original": order,
            "is_fullwidth": "1",
            "note_url": reverse("admin:orders-card-note", args=[order.pk]),
            "can_add_note": self.has_change_permission(request, order)
            and request.user.has_perm("orders.add_ordernote"),
            "manual_url": reverse("admin:orders-confirm-manual", args=[order.pk])
            if self.has_manual_permission(request)
            and order.payment_status == "awaiting_manual_payment"
            else "",
            "order": order,
            "date": format_bogota_datetime(order.created_at, "es"),
            "whatsapp_url": self.whatsapp_url(order),
            "language": self.language(order),
            "destination": self.destination(order),
            "card_url": self.card_url(order),
            "status_url": reverse("admin:orders-card-status", args=[order.pk]),
            "change_url": reverse("admin:orders_order_change", args=[order.pk]),
            "certificate_url": reverse("admin:orders-certificate", args=[order.pk])
            if certificate_available(order)
            else "",
            "can_transition": self.has_change_permission(request, order)
            and self.has_fulfillment_permission(request),
            "can_notes": request.user.has_perm("orders.view_ordernote"),
            "states": [
                {
                    "value": key,
                    "label": label,
                    "disabled": key == "preparing" and order.payment_status != "approved",
                }
                for key, label in Order._meta.get_field("fulfillment_status").choices
                if key in allowed
            ],
            "pieces": [
                {
                    "name": item.name_es,
                    "sku": item.sku,
                    "url": reverse("admin:catalog_piece_change", args=[item.piece_id]),
                    "image": self.card_piece_image(item),
                    "price": format_admin_cop(item.unit_price_cents),
                    "discount": format_admin_cop(item.discount_cents),
                }
                for item in order.items.all()
            ],
            "totals": [
                ("Subtotal", self.subtotal_cop(order)),
                ("Descuento", self.discount_cop(order)),
                ("Envío", self.shipping_cop(order)),
                ("Certificado", self.certificate_cop(order)),
            ],
            "total": self.total_cop(order),
            "history": history,
            "form": CardFulfillmentForm(order=order),
            **extra,
        }

    @staticmethod
    def card_piece_image(item):
        from apps.core.admin_presentation import thumbnail_url

        image = next((image for image in item.piece.images.all() if image.is_primary), None)
        return thumbnail_url(image) if image and image.original else item.image_path

    def change_view(self, request, object_id, form_url="", extra_context=None):
        if request.method == "GET":
            order = self.card_order(request, object_id)
            return TemplateResponse(
                request,
                "admin/orders/card_page.html",
                self.card_context(request, order, **(extra_context or {})),
            )
        return super().change_view(request, object_id, form_url, extra_context)

    def card_note(self, request, pk):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        order = self.card_order(request, pk)
        if not self.has_change_permission(request, order) or not request.user.has_perm(
            "orders.add_ordernote"
        ):
            raise PermissionDenied
        error = ""
        try:
            add_order_note(order, request.POST.get("text", ""), request=request)
        except ValidationError as exc:
            error = " ".join(exc.messages)
        order = self.card_order(request, pk)
        context = self.card_context(
            request,
            order,
            note_error=error,
            note_text=request.POST.get("text", "") if error else "",
            success="" if error else "Nota interna agregada.",
        )
        template = (
            "admin/orders/card.html"
            if request.headers.get("X-Order-Card")
            else "admin/orders/card_page.html"
        )
        return TemplateResponse(request, template, context, status=422 if error else 200)

    def card_page(self, request, pk):
        if request.method != "GET":
            return HttpResponseNotAllowed(["GET"])
        order = self.card_order(request, pk)
        template = "admin/orders/card.html"
        if request.GET.get("print") == "1":
            template = "admin/orders/card_print.html"
        elif request.GET.get("full") == "1":
            template = "admin/orders/card_page.html"
        context = self.card_context(request, order)
        if request.GET.get("print") == "1":
            context.update(print_mode=True, can_transition=False, can_add_note=False)
        return TemplateResponse(request, template, context)

    def card_status(self, request, pk):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        order = self.card_order(request, pk)
        if not self.has_change_permission(request, order) or not self.has_fulfillment_permission(
            request
        ):
            raise PermissionDenied
        form = CardFulfillmentForm(request.POST, order=order)
        success = ""
        if form.is_valid():
            data = form.cleaned_data
            try:
                with transaction.atomic():
                    locked = Order.objects.select_for_update().get(pk=order.pk)
                    if locked.fulfillment_status != data["expected_status"]:
                        raise ValidationError(
                            "El estado cambió mientras revisabas el pedido. "
                            "Cierra y vuelve a abrirlo."
                        )
                    transition_status(
                        locked,
                        "fulfillment_status",
                        data["target"],
                        request=request,
                        note=data["note"],
                        carrier=data["carrier"],
                        tracking_number=data["tracking_number"],
                        tracking_url=data["tracking_url"],
                        notify=data["notify"],
                    )
                notified = (
                    data["notify"]
                    and bool(order.customer_email.strip())
                    and data["target"] != "returned"
                )
                success = (
                    "Estado actualizado. El correo al cliente quedó en cola de envío."
                    if notified
                    else "Estado actualizado sin notificar al cliente."
                )
                order = self.card_order(request, pk)
            except ValidationError as exc:
                form.add_error(None, " ".join(exc.messages))
            except DomainError:
                form.add_error(
                    None,
                    "No se puede realizar este cambio. "
                    "Revisa el estado actual y que el pago esté aprobado.",
                )
        context = self.card_context(request, order, success=success)
        if not success:
            context.update(form=form, confirming=True, selected_target=request.POST.get("target"))
        template = (
            "admin/orders/card.html"
            if request.headers.get("X-Order-Card")
            else "admin/orders/card_page.html"
        )
        response = TemplateResponse(request, template, context, status=200 if success else 422)
        if success:
            response["X-Order-Updated"] = "1"
        return response

    def changelist_view(self, request, extra_context=None):
        clean_request = copy(request)
        clean_request.GET = request.GET.copy()
        clean_request.GET.pop("pedido", None)
        response = super().changelist_view(clean_request, extra_context)
        if (
            hasattr(response, "context_data")
            and response.context_data
            and "cl" in response.context_data
        ):
            count_request = copy(clean_request)
            count_request.GET = clean_request.GET.copy()
            for key in (
                "p",
                "fulfillment_status",
                "fulfillment_status__exact",
                "fulfillment_status__in",
                "payment_status",
                "payment_status__exact",
            ):
                count_request.GET.pop(key, None)
            base = self.get_changelist_instance(count_request).queryset
            specs = [
                ("Todos", {}),
                (
                    "Por preparar",
                    {
                        "fulfillment_status__exact": "unfulfilled",
                        "payment_status__exact": "approved",
                    },
                ),
                ("En preparación", {"fulfillment_status__exact": "preparing"}),
                ("Enviados", {"fulfillment_status__exact": "shipped"}),
                ("Entregados", {"fulfillment_status__exact": "delivered"}),
                ("Cancelados/devueltos", {"fulfillment_status__in": "cancelled,returned"}),
            ]
            tabs = []
            for label, filters in specs:
                query = count_request.GET.copy()
                query.update(filters)
                lookup = {
                    key: value.split(",") if key.endswith("__in") else value
                    for key, value in filters.items()
                }
                active = all(clean_request.GET.get(key) == value for key, value in filters.items())
                if not filters:
                    active = not any(
                        key.startswith("fulfillment_status") for key in clean_request.GET
                    )
                tabs.append(
                    {
                        "label": label,
                        "url": "?" + query.urlencode(),
                        "count": base.filter(**lookup).count(),
                        "active": active,
                    }
                )
            cl = response.context_data["cl"]
            page = cl.page_num
            response.context_data.update(
                order_tabs=tabs,
                page_number=page,
                page_total=cl.paginator.num_pages,
                previous_url=cl.get_query_string({"p": page - 1}) if page > 1 else "",
                next_url=cl.get_query_string({"p": page + 1})
                if page < cl.paginator.num_pages
                else "",
            )
        return response
