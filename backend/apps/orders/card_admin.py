"""Admin order card: server rendering is shared by the drawer, page and print view."""

from copy import copy

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Prefetch
from django.http import Http404, HttpResponse, HttpResponseNotAllowed
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
                "items__piece__reservations",
                "items__piece__status_changes",
                "payment_attempts",
                "payment_events",
                "notes__author",
                "incidents__created_by",
                "incidents__resolved_by",
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
        from apps.notifications.presentation import communication_rows

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
        can_cancel = request.user.has_perm("orders.cancel_order")
        incidents = [
            {
                "incident": incident,
                "can_resolve": incident.status == "open"
                and request.user.has_perm(incident.resolution_permission),
            }
            for incident in order.incidents.all()
        ]
        return {
            **self.admin_site.each_context(request),
            "title": f"Pedido {order.number}",
            "full_page": request.headers.get("X-Order-Page") == "1",
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
            "incidents": incidents,
            "open_incidents": [
                row["incident"] for row in incidents if row["incident"].status == "open"
            ],
            "can_open_incident": request.user.has_perm("orders.add_orderincident"),
            "incident_url": reverse("admin:orders-card-incident", args=[order.pk]),
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
            and (self.has_fulfillment_permission(request) or can_cancel),
            "can_notes": request.user.has_perm("orders.view_ordernote"),
            "states": [
                {
                    "value": key,
                    "label": label,
                    "disabled": key == "preparing" and order.payment_status != "approved",
                }
                for key, label in Order._meta.get_field("fulfillment_status").choices
                if key in allowed and (key != "cancelled" or can_cancel)
            ],
            "pieces": [
                {
                    "id": item.piece_id,
                    "held": order.fulfillment_status == "cancelled"
                    and item.piece.sale_state == "reserved"
                    and not any(r.status == "active" for r in item.piece.reservations.all()),
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
            "payments": self.payment_rows(order),
            "payment_events": self.payment_event_rows(order),
            "can_release_piece": request.user.has_perm("catalog.publish_piece")
            and request.user.has_perm("catalog.change_piece"),
            "piece_decision_url": reverse("admin:orders-card-piece", args=[order.pk]),
            "communications": communication_rows(
                order, can_manage=request.user.has_perm("notifications.resend_notificationdelivery")
            ),
            "communication_url": reverse("admin:orders-card-communication", args=[order.pk]),
            "form": CardFulfillmentForm(order=order, can_cancel=can_cancel),
            **extra,
        }

    @staticmethod
    def payment_rows(order):
        states = {
            "PENDING": "Pendiente",
            "APPROVED": "Aprobado",
            "DECLINED": "Rechazado",
            "ERROR": "Error",
            "VOIDED": "Anulado",
        }
        methods = {
            "CARD": "Tarjeta",
            "PSE": "PSE",
            "NEQUI": "Nequi",
            "BANCOLOMBIA_TRANSFER": "Transferencia Bancolombia",
            "BANCOLOMBIA_COLLECT": "Bancolombia",
            "DAVIPLATA": "Daviplata",
        }
        return [
            {
                "reference": a.reference,
                "method": "Manual"
                if a.channel == "manual"
                else methods.get(a.payment_method_type, "Wompi"),
                "status": states.get(a.status, "En revisión"),
                "amount": format_admin_cop(a.amount_cents),
                "created": format_bogota_datetime(a.created_at, "es"),
                "updated": format_bogota_datetime(a.updated_at, "es"),
            }
            for a in order.payment_attempts.all()
        ]

    @staticmethod
    def payment_event_rows(order):
        outcomes = {
            "applied": "Aplicado",
            "duplicate": "Ya recibido",
            "rejected_checksum": "Firma rechazada",
            "mismatch": "Datos no coinciden",
            "unknown_reference": "Referencia desconocida",
            "ignored_event": "Recibido sin aplicar",
        }
        states = {
            "PENDING": "Pendiente",
            "APPROVED": "Aprobado",
            "DECLINED": "Rechazado",
            "ERROR": "Error",
            "VOIDED": "Anulado",
        }
        return [
            {
                "date": format_bogota_datetime(e.received_at, "es"),
                "result": outcomes.get(e.outcome, "En revisión"),
                "status": states.get(e.status, "En revisión"),
            }
            for e in order.payment_events.all()
        ]

    def card_piece_decision(self, request, pk):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        from django.shortcuts import get_object_or_404

        from apps.inventory.services import decide_cancelled_piece

        order = self.card_order(request, pk)
        if not self.has_change_permission(request, order):
            raise PermissionDenied
        error = ""
        try:
            if request.POST.get("confirm") != "yes":
                raise ValidationError("Confirma qué deseas hacer con la pieza.")
            action = request.POST.get("decision")
            if action not in {"release", "retain"}:
                raise ValidationError("Selecciona una decisión válida.")
            piece_id = request.POST.get("piece_id", "")
            if not piece_id.isdecimal() or len(piece_id) > 18:
                raise Http404
            item = get_object_or_404(order.items, piece_id=piece_id)
            decide_cancelled_piece(
                item.piece_id, actor=request.user, order_id=order.pk, release=action == "release"
            )
        except ValidationError as exc:
            error = " ".join(exc.messages)
        response = TemplateResponse(
            request,
            "admin/orders/card.html"
            if request.headers.get("X-Order-Card")
            else "admin/orders/card_page.html",
            self.card_context(
                request,
                self.card_order(request, pk),
                incident_error=error,
                success="" if error else "Decisión guardada.",
                full_page=not request.headers.get("X-Order-Card"),
            ),
            status=422 if error else 200,
        )
        if not error:
            response["X-Order-Updated"] = "1"
        return response

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
                self.card_context(request, order, full_page=True, **(extra_context or {})),
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
        context = self.card_context(request, order, full_page=request.GET.get("full") == "1")
        if request.GET.get("print") == "1":
            context.update(print_mode=True, can_transition=False, can_add_note=False)
        return TemplateResponse(request, template, context)

    def card_status(self, request, pk):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        order = self.card_order(request, pk)
        permission = (
            "orders.cancel_order"
            if request.POST.get("target") == "cancelled"
            else "orders.change_fulfillment"
        )
        if not self.has_change_permission(request, order) or not request.user.has_perm(permission):
            raise PermissionDenied
        if request.POST.get("expected_status") != order.fulfillment_status:
            return TemplateResponse(
                request,
                "admin/orders/card.html"
                if request.headers.get("X-Order-Card")
                else "admin/orders/card_page.html",
                self.card_context(request, order, incident_error="El pedido cambió, recarga."),
                status=422,
            )
        form = CardFulfillmentForm(
            request.POST, order=order, can_cancel=request.user.has_perm("orders.cancel_order")
        )
        success = ""
        if form.is_valid():
            data = form.cleaned_data
            try:
                if data["target"] == "cancelled":
                    from .services import cancel_order

                    cancel_order(
                        order,
                        actor=request.user,
                        reason=data["note"],
                        notify=data["notify"],
                        include_reason=data["include_reason"],
                        expected_status=data["expected_status"],
                    )
                else:
                    transition_status(
                        order,
                        "fulfillment_status",
                        data["target"],
                        request=request,
                        note=data["note"],
                        carrier=data["carrier"],
                        tracking_number=data["tracking_number"],
                        tracking_url=data["tracking_url"],
                        notify=data["notify"],
                        expected_status=data["expected_status"],
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

    def card_incident(self, request, pk):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        from django.shortcuts import get_object_or_404

        from .incidents import open_manual_incident, resolve_incident

        order = self.card_order(request, pk)
        if not self.has_change_permission(request, order):
            raise PermissionDenied
        error = ""
        try:
            if request.POST.get("incident_id"):
                incident = get_object_or_404(order.incidents, pk=request.POST["incident_id"])
                if request.POST.get("confirm") != "yes":
                    raise ValidationError("Confirma que deseas resolver esta incidencia.")
                resolve_incident(
                    incident,
                    actor=request.user,
                    note=request.POST.get("note", ""),
                    notify=request.POST.get("notify") == "on",
                )
            else:
                open_manual_incident(
                    order,
                    actor=request.user,
                    detail=request.POST.get("detail", ""),
                    blocking=request.POST.get("blocking") == "on",
                )
        except ValidationError as exc:
            error = " ".join(exc.messages)
        order = self.card_order(request, pk)
        response = TemplateResponse(
            request,
            "admin/orders/card.html"
            if request.headers.get("X-Order-Card")
            else "admin/orders/card_page.html",
            self.card_context(
                request,
                order,
                incident_error=error,
                success="" if error else "Incidencia actualizada.",
            ),
            status=422 if error else 200,
        )
        if not error:
            response["X-Order-Updated"] = "1"
        return response

    def card_communication(self, request, pk):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        from django.shortcuts import get_object_or_404

        from apps.notifications.services import resend, send_copy

        order = self.card_order(request, pk)
        if not request.user.has_perm("notifications.resend_notificationdelivery"):
            raise PermissionDenied
        delivery_id = request.POST.get("delivery_id", "")
        if not delivery_id.isdecimal():
            raise Http404
        delivery = get_object_or_404(order.deliveries, pk=delivery_id)
        error = ""
        try:
            if request.POST.get("confirm") != "yes":
                raise ValidationError("Confirma el envío de esta comunicación.")
            if request.POST.get("action") == "copy":
                send_copy(delivery.pk, request=request)
            elif request.POST.get("action") == "resend":
                if not resend(delivery.pk, request=request):
                    raise ValidationError(
                        "Este aviso no se puede reenviar con la configuración actual."
                    )
            else:
                raise ValidationError("Selecciona una acción válida.")
        except ValidationError as exc:
            error = " ".join(exc.messages)
        return TemplateResponse(
            request,
            "admin/orders/card.html"
            if request.headers.get("X-Order-Card")
            else "admin/orders/card_page.html",
            self.card_context(
                request,
                self.card_order(request, pk),
                communication_error=error,
                success="" if error else "Comunicación en cola de envío.",
            ),
            status=422 if error else 200,
        )

    def card_email(self, request, pk, delivery_id):
        if request.method != "GET":
            return HttpResponseNotAllowed(["GET"])
        from django.shortcuts import get_object_or_404

        from apps.notifications.rendering import render_email

        order = self.card_order(request, pk)
        delivery = get_object_or_404(order.deliveries, pk=delivery_id, channel="email")
        response = HttpResponse(render_email(delivery, order).html)
        response["Content-Security-Policy"] = (
            "sandbox; default-src 'none'; style-src 'unsafe-inline'; "
            "img-src https: http:; base-uri 'none'"
        )
        response["Cache-Control"] = "private, no-store"
        response["Referrer-Policy"] = "no-referrer"
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
                "center",
                "fulfillment_status",
                "fulfillment_status__exact",
                "fulfillment_status__in",
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
                query.update(
                    {
                        key: value
                        for key, value in filters.items()
                        if not key.startswith("payment_status")
                    }
                )
                if label == "Por preparar":
                    query["center"] = "prepare"
                lookup = {
                    key: value.split(",") if key.endswith("__in") else value
                    for key, value in filters.items()
                }
                active = all(clean_request.GET.get(key) == value for key, value in filters.items())
                if label == "Por preparar" and clean_request.GET.get("center") == "prepare":
                    active = True
                if not filters:
                    active = clean_request.GET.get("center") != "prepare" and not any(
                        key.startswith("fulfillment_status") for key in clean_request.GET
                    )
                tab_base = base
                if label == "Por preparar":
                    from django.db.models import Exists, OuterRef

                    from .models import OrderIncident

                    tab_base = tab_base.filter(
                        ~Exists(
                            OrderIncident.objects.filter(
                                order_id=OuterRef("pk"), status="open", blocking=True
                            )
                        )
                    )
                tabs.append(
                    {
                        "label": label,
                        "url": "?" + query.urlencode(),
                        "count": tab_base.filter(**lookup).count(),
                        "active": active,
                    }
                )
            cl = response.context_data["cl"]
            page = cl.page_num
            from .metrics import order_center_metrics

            response.context_data.update(
                center_metrics=order_center_metrics(request.GET.get("period", "today")),
                center_period=request.GET.get("period", "today"),
                order_tabs=tabs,
                page_number=page,
                page_total=cl.paginator.num_pages,
                previous_url=cl.get_query_string({"p": page - 1}) if page > 1 else "",
                next_url=cl.get_query_string({"p": page + 1})
                if page < cl.paginator.num_pages
                else "",
            )
        return response
