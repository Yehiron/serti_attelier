from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse

from apps.core.formatting import format_bogota_datetime, format_cop, place_name
from apps.core.routes import href
from apps.core.selectors import get_solo
from apps.orders.models import Order
from apps.orders.selectors import manual_instructions
from apps.payments.models import PaymentEvent

from .models import NotificationDelivery


@dataclass(frozen=True)
class EmailContent:
    subject: str
    text: str
    html: str
    reply_to: str


def attention_reason(order: Order) -> str:
    # Payment event outcomes are fixed internal codes, never provider text.
    has_mismatch = PaymentEvent.objects.filter(order=order, outcome="mismatch").exists()
    if order.payment_status == "voided":
        return "Pago anulado después de la aprobación"
    if has_mismatch:
        return "Discrepancia de monto, moneda, transacción o estado de pago"
    return "Pieza no disponible al aprobar el pago"


def order_context(order: Order, locale: str) -> dict[str, Any]:
    config = get_solo()
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
        "site_url": settings.PUBLIC_SITE_URL,
        "monogram_url": f"{settings.PUBLIC_SITE_URL}/brand/monogram-email.png",
        "order_url": settings.PUBLIC_SITE_URL + href("order", locale, order),
        "catalog_url": settings.PUBLIC_SITE_URL + href("catalog", locale),
        "admin_url": settings.PUBLIC_SITE_URL
        + reverse("admin:orders_order_change", args=[order.pk]),
        "date": format_bogota_datetime(order.created_at, locale),
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
        "purchase_status": {"approved": "Pago aprobado", "voided": "Pago anulado"}.get(
            order.payment_status, "Pendiente de pago"
        )
        if locale == "es"
        else {"approved": "Payment approved", "voided": "Payment voided"}.get(
            order.payment_status, "Awaiting payment"
        ),
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
    context = order_context(order, delivery.locale)
    if delivery.audience == "serti":
        title = {
            "order_paid": "Nuevo pedido",
            "manual_payment_instructions": "Nuevo pedido con pago manual",
            "needs_attention": "URGENTE · Pedido requiere atención",
        }[delivery.event]
        subject = f"[SERTI] {title} {order.number} · {context['total']}"
    else:
        titles = {
            "es": {
                "order_paid": "Confirmación de compra",
                "manual_payment_instructions": "Instrucciones de pago",
                "reservation_expired": "Tu reserva venció",
            },
            "en": {
                "order_paid": "Purchase confirmation",
                "manual_payment_instructions": "Payment instructions",
                "reservation_expired": "Your reservation expired",
            },
        }
        title = titles[delivery.locale][delivery.event]
        subject = f"SERTI · {title} {order.number}"
    context.update(title=title, event=delivery.event)
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
