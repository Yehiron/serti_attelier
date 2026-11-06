from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse

from apps.core.formatting import format_bogota_datetime, format_cop, place_name
from apps.core.routes import href
from apps.core.selectors import get_solo
from apps.orders.models import Order, OrderIncident
from apps.orders.selectors import manual_instructions
from apps.payments.models import PaymentEvent

from .models import EVENT_LABELS, NotificationDelivery

EN_TITLES = {
    "order_received": "Order received — payment in progress",
    "payment_issue": "Payment under review",
    "order_paid": "Payment approved",
    "order_preparing": "In preparation",
    "order_shipped": "Order shipped",
    "order_delivered": "Order delivered",
    "order_cancelled": "Order cancelled",
    "manual_payment_instructions": "Payment instructions",
    "reservation_expired": "Reservation expired",
    "needs_attention": "Incident opened",
    "incident_resolved": "Incident resolved",
}
EN_INCIDENTS = {
    "no_piece": "Payment received without an available piece",
    "cancelled_payment": "Payment received for a cancelled order",
    "refund_pending": "Refund pending",
    "amount_mismatch": "Amount or currency mismatch",
    "voided_shipped": "Payment voided after shipping",
    "suspicious": "Unusual payment event",
    "other": "Other",
}


@dataclass(frozen=True)
class EmailContent:
    subject: str
    text: str
    html: str
    reply_to: str


def attention_reason(order: Order) -> str:
    incident = order.incidents.filter(status="open").first()
    if incident:
        return str(incident.get_kind_display())
    # Payment event outcomes are fixed internal codes, never provider text.
    has_mismatch = PaymentEvent.objects.filter(order=order, outcome="mismatch").exists()
    if order.payment_status == "voided":
        return "Pago anulado después de la aprobación"
    if has_mismatch:
        return "Discrepancia de monto, moneda, transacción o estado de pago"
    return "Pieza no disponible al aprobar el pago"


def order_context(order: Order, locale: str) -> dict[str, Any]:
    config = get_solo()
    site_url = settings.PUBLIC_SITE_URL.rstrip("/")
    public_logo = urlsplit(site_url).scheme in {"http", "https"} and bool(urlsplit(site_url).netloc)
    municipality = order.shipping_municipality
    destination = f"{place_name(municipality.name)}, {place_name(municipality.department.name)}"
    whatsapp = (
        f"https://wa.me/{config.whatsapp_number}?"
        + urlencode(
            {
                "text": "Hola SERTI, quisiera crear una pieza única."
                if locale == "es"
                else "Hello SERTI, I would like to create a unique piece."
            }
        )
        if config.whatsapp_number
        else ""
    )
    return {
        "order": order,
        "locale": locale,
        "order_label": "Ver mi pedido" if locale == "es" else "View my order",
        "admin_label": "Administrar pedido" if locale == "es" else "Manage order",
        "reference_label": "Referencia" if locale == "es" else "Reference",
        "address_label": "Dirección de entrega" if locale == "es" else "Delivery address",
        "status_label": "Estado actual" if locale == "es" else "Current status",
        "l_subtotal": "Subtotal",
        "l_discount": "Descuento" if locale == "es" else "Discount",
        "l_shipping": "Envío" if locale == "es" else "Shipping",
        "l_certificate": "Certificado de autenticidad"
        if locale == "es"
        else "Certificate of authenticity",
        "l_total": "Total · COP",
        "site_url": settings.PUBLIC_SITE_URL,
        "monogram_url": f"{site_url}/brand/monogram-email.png" if public_logo else "",
        "order_url": settings.PUBLIC_SITE_URL + href("order", locale, order),
        "catalog_url": settings.PUBLIC_SITE_URL + href("catalog", locale),
        "admin_url": settings.PUBLIC_SITE_URL
        + reverse("admin:orders_order_change", args=[order.pk]),
        "date": format_bogota_datetime(order.created_at, locale),
        "paid_date": format_bogota_datetime(order.paid_at, locale) if order.paid_at else "",
        "current_status": str(order.get_fulfillment_status_display())
        if locale == "es"
        else {
            "unfulfilled": "Not yet in preparation",
            "preparing": "In preparation",
            "shipped": "Shipped",
            "delivered": "Delivered",
            "cancelled": "Cancelled",
            "returned": "Returned",
        }.get(order.fulfillment_status, ""),
        "deadline": format_bogota_datetime(order.reservation_expires_at, locale)
        if order.reservation_expires_at
        else "",
        "instructions": manual_instructions(order) or "",
        "total": format_cop(order.total_cents, locale),
        "subtotal": format_cop(order.subtotal_cents, locale),
        "discount": format_cop(order.discount_cents, locale),
        "shipping": format_cop(order.shipping_cents, locale),
        "certificate_price": format_cop(order.certificate_cents, locale),
        "certificate": ("Sí" if order.wants_certificate else "No")
        if locale == "es"
        else ("Yes" if order.wants_certificate else "No"),
        "destination": destination,
        "address": ", ".join(
            filter(
                None,
                [
                    order.shipping_address_line,
                    order.shipping_address_extra,
                    destination,
                    "Colombia",
                ],
            )
        ),
        "support_email": config.support_email,
        "whatsapp_url": whatsapp,
        "instagram_url": config.instagram_url,
        "facebook_url": config.facebook_url,
        "reason": attention_reason(order),
        "purchase_status": {
            "approved": "Pago aprobado",
            "voided": "Pago anulado",
            "pending": "Pago en proceso",
            "awaiting_manual_payment": "Pendiente de pago manual",
            "declined": "Pago rechazado",
            "error": "Pago por revisar",
            "expired": "Reserva vencida",
        }.get(order.payment_status, "Pendiente de pago")
        if locale == "es"
        else {
            "approved": "Payment approved",
            "voided": "Payment voided",
            "pending": "Payment in progress",
            "awaiting_manual_payment": "Awaiting manual payment",
            "declined": "Payment declined",
            "error": "Payment under review",
            "expired": "Reservation expired",
        }.get(order.payment_status, "Awaiting payment"),
        "items": [
            {
                "name": getattr(item, f"name_{locale}") or item.name_es,
                "number": item.piece_number or "",
                "sku": item.sku,
                "price": format_cop(item.unit_price_cents, locale),
                "discount": format_cop(item.discount_cents, locale),
            }
            for item in order.items.all()
        ],
    }


def render_email(delivery: NotificationDelivery, order: Order) -> EmailContent:
    # A persisted rendering is also the retry/copy source and the historical preview.
    if delivery.payload.get("rendered"):
        return EmailContent(**delivery.payload["rendered"])
    context = order_context(order, delivery.locale)
    title = (EVENT_LABELS if delivery.locale == "es" else EN_TITLES)[delivery.event]
    if delivery.event == "order_received" and delivery.locale == "es":
        title = "Recibimos tu pedido — pago en proceso"
    subject = f"SERTI · {'Pedido' if delivery.locale == 'es' else 'Order'} {order.number} · {title}"
    metadata = delivery.payload.get("metadata", {})
    kind = metadata.get("incident_kind")
    incident_label = (
        dict(OrderIncident.Kind.choices).get(kind, "")
        if delivery.locale == "es"
        else EN_INCIDENTS.get(kind, "")
    )
    context.update(
        title=title,
        event=delivery.event,
        internal=delivery.audience == "serti",
        cancellation_reason=metadata.get("cancellation_reason", ""),
        refund_due=metadata.get("refund_due", bool(order.paid_at)),
        incident_label=incident_label,
    )
    prefix = f"emails/{delivery.locale}/{delivery.template}"
    return EmailContent(
        subject,
        render_to_string(prefix + ".txt", context),
        render_to_string(prefix + ".html", context),
        context["support_email"],
    )


def whatsapp_parameters(order: Order, event: str) -> list[str]:
    context = order_context(order, "es")
    parameters = [
        str(order.number),
        order.customer_name.split()[0] if order.customer_name else "—",
        ", ".join(item["name"] for item in context["items"])[:300],
        context["total"],
        context["destination"],
        context["certificate"],
        context["admin_url"],
    ]
    if event == "needs_attention":
        parameters.append(context["reason"])
    return parameters
