from __future__ import annotations

from typing import Any

from django.utils.translation import override

from apps.cms.models import Page
from apps.cms.selectors import localized
from apps.core.formatting import format_bogota_datetime, format_cop, place_name
from apps.core.selectors import get_solo

from .models import Order


def legal_versions() -> dict[str, int | None]:
    versions: dict[str, int | None] = {"terms": None, "privacy": None}
    for page in Page.objects.filter(status="published", kind__in=versions).prefetch_related(
        "revisions"
    ):
        revision = next(iter(page.revisions.all()), None)
        if revision:
            versions[page.kind] = revision.version
    return versions


def manual_instructions(order: Order) -> str | None:
    if order.payment_channel != "manual":
        return None
    template = localized(get_solo(), "manual_payment_instructions", order.locale)
    deadline = order.reservation_expires_at
    return template.format(
        number=order.number,
        total=format_cop(order.total_cents, order.locale),
        deadline=format_bogota_datetime(deadline, order.locale) if deadline else "",
    )


def created_data(order: Order) -> dict[str, Any]:
    return {
        "number": order.number,
        "public_token": order.public_token,
        "payment_channel": order.payment_channel,
        "payment_status": order.payment_status,
        "total_cents": order.total_cents,
        "reservation_expires_at": order.reservation_expires_at,
        "manual_instructions": manual_instructions(order),
    }


def order_detail(token: str) -> dict[str, Any]:
    from .exceptions import CheckoutError

    order = (
        Order.objects.select_related("shipping_municipality__department")
        .prefetch_related("items")
        .filter(public_token=token)
        .first()
    )
    if order is None:
        raise CheckoutError("order_not_found", status=404)
    with override(order.locale):
        items = [
            {
                "sku": i.sku,
                "name": getattr(i, f"name_{order.locale}") or i.name_es,
                "image": (i.image_snapshot or {}).get(order.locale),
                "unit_price_cents": i.unit_price_cents,
                "discount_cents": i.discount_cents,
                "piece_number": i.piece_number,
            }
            for i in order.items.all()
        ]
    fields = (
        "number",
        "created_at",
        "locale",
        "payment_channel",
        "payment_status",
        "fulfillment_status",
        "subtotal_cents",
        "discount_cents",
        "shipping_cents",
        "certificate_cents",
        "total_cents",
        "currency",
        "wants_certificate",
        "reservation_expires_at",
    )
    return {
        **{f: getattr(order, f) for f in fields},
        "items": items,
        "shipping": {
            "department": place_name(order.shipping_municipality.department.name),
            "municipality": place_name(order.shipping_municipality.name),
        },
        "manual_instructions": manual_instructions(order),
    }
