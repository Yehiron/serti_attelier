from __future__ import annotations

from datetime import timedelta
from typing import Any, cast

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db.models import Exists, OuterRef, Subquery
from django.utils import timezone
from django.utils.translation import override

from apps.cms.models import Page
from apps.cms.selectors import localized
from apps.core.formatting import format_bogota_datetime, format_cop, place_name
from apps.core.selectors import get_solo

from .models import Order, OrderIncident, OrderStatusChange


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
    from apps.payments.services import payment_data

    return {
        **payment_data(order, include_customer=True),
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
        .annotate(**tracking_annotations())
        .prefetch_related("items")
        .filter(public_token=token)
        .first()
    )
    if order is None or tracking_expired(order):
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
    from apps.payments.services import payment_data

    return {
        **payment_data(order),
        **{f: getattr(order, f) for f in fields},
        "items": items,
        "fulfillment": fulfillment_data(order),
        "payment_review": cast(Any, order)._payment_review,
        "shipping": {
            "department": place_name(order.shipping_municipality.department.name),
            "municipality": place_name(order.shipping_municipality.name),
        },
        "manual_instructions": manual_instructions(order),
    }


def tracking_annotations():
    changes = OrderStatusChange.objects.filter(order_id=OuterRef("pk"))
    result = {
        f"_{state}_at": Subquery(
            changes.filter(field="fulfillment_status", to_state=state)
            .order_by("-at")
            .values("at")[:1]
        )
        for state in ("preparing", "shipped", "delivered", "cancelled", "returned")
    }
    result["_ever_paid"] = Exists(changes.filter(field="payment_status", to_state="approved"))
    result["_payment_review"] = Exists(
        OrderIncident.objects.filter(order_id=OuterRef("pk"), status="open").exclude(kind="other")
    )
    return result


def status_date(order: Order, state: str):
    if hasattr(order, f"_{state}_at"):
        return getattr(order, f"_{state}_at")
    return next(
        (
            change.at
            for change in sorted(order.status_changes.all(), key=lambda c: c.at, reverse=True)
            if change.field == "fulfillment_status" and change.to_state == state
        ),
        None,
    )


def tracking_expired(order: Order) -> bool:
    terminal = order.fulfillment_status
    if terminal in ("delivered", "cancelled", "returned"):
        at = (order.delivered_at if terminal == "delivered" else None) or status_date(
            order, terminal
        )
        # Legacy records without history: use the last known modification conservatively.
        at = at or order.updated_at
        return timezone.now() > at + timedelta(days=settings.ORDER_TRACKING_TTL_DAYS)
    if (
        not order.paid_at
        and order.payment_status != "approved"
        and not (
            order._ever_paid
            if hasattr(order, "_ever_paid")
            else order.status_changes.filter(field="payment_status", to_state="approved").exists()
        )
        and order.reservation_expires_at
    ):
        return timezone.now() > order.reservation_expires_at + timedelta(days=30)
    return False


def fulfillment_data(order: Order) -> dict[str, Any]:
    shipped = order.shipped_at or status_date(order, "shipped")
    delivered = order.delivered_at or status_date(order, "delivered")
    milestones = [("received", order.created_at), ("paid", order.paid_at)]
    if order.fulfillment_status == "cancelled":
        milestones.append(("cancelled", status_date(order, "cancelled")))
    else:
        milestones.extend(
            [
                ("preparing", status_date(order, "preparing")),
                ("shipped", shipped),
                ("delivered", delivered),
            ]
        )
        if order.fulfillment_status == "returned":
            milestones.append(("returned", status_date(order, "returned")))
    result = {
        "status": order.fulfillment_status,
        "carrier": order.carrier,
        "tracking_number": order.tracking_number,
        "shipped_at": shipped,
        "delivered_at": delivered,
        "timeline": [{"key": key, "label_key": key, "at": at} for key, at in milestones],
    }
    try:
        URLValidator(schemes=["http", "https"])(order.tracking_url)
    except ValidationError:
        pass
    else:
        result["tracking_url"] = order.tracking_url
    return result
