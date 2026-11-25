from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any, cast
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import Field, Q
from django.http import HttpRequest
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import override

from apps.accounts.models import User
from apps.audit.services import record
from apps.cart.models import Cart
from apps.cart.selectors import pieces
from apps.cart.services import clean_cart, empty_cart
from apps.catalog.api.serializers import PieceListSerializer
from apps.catalog.models import Piece
from apps.cms.selectors import localized
from apps.core.models import Municipality
from apps.core.selectors import get_solo
from apps.inventory.services import PieceNotAvailable, reserve_piece
from apps.pricing.services import CouponRules, PricedItem, Quote, quote
from apps.promotions.models import Coupon
from apps.promotions.selectors import coupon_rules
from apps.promotions.services import email_digest

from . import events
from .exceptions import CheckoutError
from .models import Order, OrderItem, OrderNote, OrderStatusChange
from .selectors import legal_versions
from .serializers import OrderInputSerializer
from .transitions import FULFILLMENT_TRANSITIONS, PAYMENT_TRANSITIONS


def request_digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def compute_quote(
    items: list[Piece],
    code: str,
    *,
    wants_certificate: bool,
    email_hash: str | None = None,
    lock: bool = False,
) -> tuple[Quote, Coupon | None]:
    coupon = None
    rules = None
    if code:
        query = Coupon.objects.select_for_update() if lock else Coupon.objects.all()
        coupon = query.filter(code=code.strip().upper()).first()
        rules = (
            coupon_rules(coupon, email_hash)
            if coupon
            else CouponRules(code.strip().upper(), "fixed", 1, is_active=False)
        )
    config = get_solo()
    result = quote(
        [
            PricedItem(
                p.sku,
                p.name,
                p.price_cents,
                p.sale_price_cents,
                p.category_id,
                frozenset(c.pk for c in p.collections.all()),
            )
            for p in items
        ],
        rules,
        wants_certificate=wants_certificate,
        certificate_cents=config.certificate_price_cents,
        email_hash=email_hash,
        now=timezone.now(),
    )
    from dataclasses import replace

    from apps.payments.wompi import is_configured

    if not is_configured():
        result = replace(
            result, payment_channels=tuple(c for c in result.payment_channels if c != "wompi")
        )
    return result, coupon


def _replay(order: Order, digest: str) -> tuple[Order, bool]:
    if order.request_hash != digest:
        raise CheckoutError("idempotency_conflict", status=409)
    return order, False


@transaction.atomic
def create_order(
    cart: Cart | None, payload: dict[str, Any], *, idempotency_key: UUID, request: HttpRequest
) -> tuple[Order, bool]:
    digest = request_digest(payload)
    # PostgreSQL serializes a UUID key before any cart/coupon work. The lock is
    # transaction scoped and contains no PII; the unique order key remains the invariant.
    if connection.vendor == "postgresql":
        lock_id = int.from_bytes(hashlib.sha256(idempotency_key.bytes).digest()[:8], signed=True)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_id])
    existing = Order.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return _replay(existing, digest)
    if cart is None:
        raise CheckoutError("cart_empty")
    # Serializes simultaneous submissions from this browser, including replay after emptying.
    Cart.objects.select_for_update().get(pk=cart.pk)
    existing = Order.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return _replay(existing, digest)
    serializer = OrderInputSerializer(data=payload)
    if not serializer.is_valid():
        raise CheckoutError("validation_error", errors=serializer.errors)
    data = serializer.validated_data
    versions = legal_versions()
    if any(
        versions[k] is None or data.get(f"accepted_{k}_version") != versions[k] for k in versions
    ):
        raise CheckoutError("consent_required")
    municipality = Municipality.objects.filter(pk=data["shipping"]["municipality_code"]).first()
    if municipality is None:
        raise CheckoutError(
            "validation_error",
            errors={
                "shipping.municipality_code": [_("Selecciona un municipio válido de Colombia.")]
            },
        )
    # Lock all pieces before cleaning so a piece sold since the quote yields a conflict.
    ids = list(cart.items.values_list("piece_id", flat=True))
    locked = list(Piece.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
    for state in ("sold", "preorder", "reserved"):
        skus = [p.sku for p in locked if p.sale_state == state]
        if skus:
            raise CheckoutError(f"piece_{state}", status=409, skus=skus)
    clean_cart(cart)
    items = list(pieces(cart))
    if not items:
        raise CheckoutError("cart_empty")
    contact = data["contact"]
    email = contact["email"].strip().lower()
    hashed_email = email_digest(email)
    with override(data["locale"]):
        pricing, coupon = compute_quote(
            items,
            data.get("coupon_code", ""),
            wants_certificate=data["wants_certificate"],
            email_hash=hashed_email,
            lock=True,
        )
    if pricing.coupon and not pricing.coupon["applied"]:
        reason = str(pricing.coupon["reason"])
        raise CheckoutError("coupon_exhausted" if reason == "coupon_used_by_email" else reason)
    config = get_solo()
    channel = data["payment_channel"]
    expires = timezone.now() + (
        timedelta(hours=config.manual_reservation_hours)
        if channel == "manual"
        else timedelta(minutes=config.online_reservation_minutes)
    )
    shipping = data["shipping"]
    try:
        with transaction.atomic():
            order = Order.objects.create(
                idempotency_key=idempotency_key,
                request_hash=digest,
                locale=data["locale"],
                customer_name=contact["name"],
                customer_email=email,
                customer_phone=contact["phone"],
                email_hash=hashed_email,
                shipping_address_line=shipping["address_line"],
                shipping_address_extra=shipping["address_extra"],
                shipping_notes=shipping["notes"],
                shipping_municipality=municipality,
                subtotal_cents=pricing.subtotal_cents,
                discount_cents=pricing.discount_cents,
                shipping_cents=0,
                certificate_cents=pricing.certificate_cents,
                total_cents=pricing.total_cents,
                coupon=coupon,
                payment_channel=channel,
                payment_status="awaiting_manual_payment" if channel == "manual" else "pending",
                wants_certificate=data["wants_certificate"],
                terms_version=data["accepted_terms_version"],
                privacy_version=data["accepted_privacy_version"],
                privacy_consent_at=timezone.now(),
                reservation_expires_at=expires,
            )
    except IntegrityError:
        existing = Order.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return _replay(existing, digest)
        raise
    order.number = f"SRT-{order.pk:06d}"
    order.save(update_fields=["number"])
    lines = {line.sku: line for line in pricing.items}
    for piece in items:
        line = lines[piece.sku]
        images = {}
        for locale in ("es", "en"):
            with override(locale):
                images[locale] = PieceListSerializer().get_image(piece)
        OrderItem.objects.create(
            order=order,
            piece=piece,
            sku=piece.sku,
            piece_number=piece.piece_number or None,
            name_es=localized(piece, "name", "es"),
            name_en=localized(piece, "name", "en"),
            attributes=piece.attributes,
            unit_price_cents=line.unit_price_cents,
            discount_cents=line.discount_cents,
            image_path=(images["es"] or {}).get("src", ""),
            image_snapshot=images,
        )
        try:
            reservation = reserve_piece(
                piece.pk,
                kind="manual" if channel == "manual" else "online",
                reference=order.number,
                expires_at=expires,
            )
        except PieceNotAvailable as exc:
            raise CheckoutError(f"piece_{exc.state}", status=409, skus=[piece.sku]) from exc
        reservation.order = order
        reservation.save(update_fields=["order"])
    if channel == "wompi":
        from apps.payments.services import create_wompi_attempt

        create_wompi_attempt(order)
    record("orders.created", obj=order, request=request, diff={"payment_channel": [None, channel]})
    if channel == "manual":
        events.manual_order_created(order.pk)
    transaction.on_commit(lambda: empty_cart(cart))
    return order, True


@transaction.atomic
def transition_status(
    order: Order,
    field: str,
    target: str,
    *,
    request: HttpRequest | None = None,
    note: str = "",
    carrier: str | None = None,
    tracking_number: str = "",
    tracking_url: str = "",
    notify: bool = True,
    expected_status: str | None = None,
) -> None:
    if (
        field == "fulfillment_status"
        and target != "cancelled"
        and (request is None or not request.user.has_perm("orders.change_fulfillment"))
    ):
        raise PermissionDenied
    if field == "fulfillment_status" and target == "cancelled":
        cancel_order(
            order,
            actor=request.user if request else None,
            reason=note,
            notify=notify,
            expected_status=expected_status,
        )
        return
    order = Order.objects.select_for_update(of=("self",)).get(pk=order.pk)
    if expected_status is not None and getattr(order, field) != expected_status:
        raise ValidationError("El pedido cambió, recarga.")
    transitions = (
        FULFILLMENT_TRANSITIONS
        if field == "fulfillment_status"
        else PAYMENT_TRANSITIONS
        if field == "payment_status"
        else {}
    )
    previous = getattr(order, field, "")
    if target not in transitions.get(previous, ()):
        raise CheckoutError("invalid_transition")
    if field == "fulfillment_status" and target in {"preparing", "shipped"}:
        validate_fulfillment(order, target)
    updates = [field, "updated_at"]
    if field == "fulfillment_status" and target == "shipped":
        order.carrier = (carrier if carrier is not None else order.carrier).strip()
        if not order.carrier:
            raise ValidationError(_("Indica la transportadora antes de enviar."))
        order.tracking_number = tracking_number.strip()
        order.tracking_url = tracking_url.strip()
        for name in ("carrier", "tracking_number", "tracking_url"):
            cast("Field[Any, Any]", order._meta.get_field(name)).clean(getattr(order, name), order)
        order.shipped_at = timezone.now()
        updates += ["carrier", "tracking_number", "tracking_url", "shipped_at"]
    if field == "fulfillment_status" and target == "delivered":
        order.delivered_at = timezone.now()
        updates.append("delivered_at")
    setattr(order, field, target)
    order.save(update_fields=updates)
    event = (
        {
            "preparing": "order_preparing",
            "shipped": "order_shipped",
            "delivered": "order_delivered",
            "cancelled": "order_cancelled",
        }.get(target)
        if field == "fulfillment_status"
        else None
    )
    notified = bool(event and notify and order.customer_email.strip())
    if field == "fulfillment_status":
        notification_note = (
            "Correo al cliente encolado." if notified else "Sin notificar al cliente."
        )
        note = f"{note.strip()}\n{notification_note}".strip()
    change = OrderStatusChange.objects.create(
        order=order,
        field=field,
        from_state=previous,
        to_state=target,
        actor=request.user if request and request.user.is_authenticated else None,
        note=note,
    )
    if notified:
        events._notify(order.pk, event, event_key=f"status:{change.pk}")
    record(
        "orders.status_changed",
        obj=order,
        actor=request.user if request else None,
        request=request,
        diff={field: [previous, target], "customer_notification_queued": [False, notified]},
    )


def expire_stale_orders() -> int:
    count = 0
    for pk in (
        Order.objects.filter(
            payment_status__in=["pending", "awaiting_manual_payment"],
            reservations__isnull=False,
        )
        .exclude(fulfillment_status="cancelled")
        .values_list("pk", flat=True)
        .distinct()
    ):
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=pk)
            if (
                order.payment_status in {"pending", "awaiting_manual_payment"}
                and not order.reservations.filter(status__in=["active", "converted"]).exists()
            ):
                transition_status(order, "payment_status", "expired", note="reservation_expired")
                events.order_expired(pk)
                count += 1
    return count


@transaction.atomic
def add_order_note(order: Order, text: str, *, request: HttpRequest) -> OrderNote:
    if not request.user.has_perm("orders.change_order") or not request.user.has_perm(
        "orders.add_ordernote"
    ):
        raise PermissionDenied
    note = OrderNote(order=order, author=cast(User, request.user), text=text.strip())
    if not note.text:
        raise ValidationError(_("Escribe una nota."))
    note.full_clean()
    note.save()
    record("orders.note_added", actor=request.user, obj=note, request=request)
    return note


def validate_fulfillment(order, target):
    action = "preparar" if target == "preparing" else "enviar"
    prefix = f"No se puede {action}: "
    if order.payment_status != "approved":
        reason = (
            "el pago fue anulado"
            if order.payment_status == "voided"
            else "el pago no está aprobado"
        )
        raise ValidationError(prefix + reason + ".")
    incident = order.incidents.filter(status="open", blocking=True).first()
    if incident:
        raise ValidationError(
            prefix + f"hay una incidencia abierta ({incident.get_kind_display()})."
        )
    items = list(order.items.order_by("piece_id"))
    locked = list(
        Piece.objects.select_for_update(of=("self",))
        .filter(pk__in=[i.piece_id for i in items])
        .order_by("pk")
    )
    owned = set(order.reservations.filter(status="converted").values_list("piece_id", flat=True))
    if not items or any(p.sale_state != "sold" or p.pk not in owned for p in locked):
        raise ValidationError(prefix + "las piezas no están vendidas a este pedido.")


def available_fulfillment_transitions(order):
    allowed = set(FULFILLMENT_TRANSITIONS.get(order.fulfillment_status, ()))
    for target in allowed & {"preparing", "shipped"}:
        try:
            with transaction.atomic():
                validate_fulfillment(order, target)
        except ValidationError:
            allowed.remove(target)
    return allowed


@transaction.atomic
def cancel_order(order, *, actor, reason, notify, expected_status, include_reason=False):
    from apps.inventory.models import PieceReservation, PieceStatusChange
    from apps.inventory.services import release_reservation

    from .incidents import open_incident
    from .models import OrderIncident

    if actor is None or not actor.has_perm("orders.cancel_order"):
        raise PermissionDenied
    reason = reason.strip()
    if len(reason) < 5 or len(reason) > 2000:
        raise ValidationError("Indica un motivo de cancelación de entre 5 y 2000 caracteres.")
    order = Order.objects.select_for_update(of=("self",)).get(pk=order.pk)
    if order.fulfillment_status != expected_status:
        raise ValidationError("El pedido cambió, recarga.")
    if order.fulfillment_status not in {"unfulfilled", "preparing"} or order.shipped_at:
        raise ValidationError("Solo se pueden cancelar pedidos sin preparar o en preparación.")
    previous = order.fulfillment_status
    # Lock in piece order, shared with approval. Never create an expiring hold for sold pieces.
    for piece in (
        Piece.objects.select_for_update(of=("self",))
        .filter(
            Q(pk__in=order.items.values("piece_id"))
            | Q(pk__in=order.reservations.values("piece_id"))
        )
        .order_by("pk")
    ):
        for reservation in order.reservations.filter(piece=piece, status="active"):
            release_reservation(reservation.pk, reason="released")
        if (
            piece.sale_state == "sold"
            and order.reservations.filter(piece=piece, status="converted").exists()
        ):
            piece.sale_state = "reserved"
            piece.sold_at = None
            piece.save(update_fields=["sale_state", "sold_at"])
            PieceReservation.objects.filter(order=order, piece=piece, status="converted").update(
                status="released"
            )
            PieceStatusChange.objects.create(
                piece=piece,
                from_state="sold",
                to_state="reserved",
                reason="admin",
                ref=order.number or "",
                actor=actor,
            )
    if order.payment_status not in {"approved", "voided", "cancelled"}:
        payment_previous = order.payment_status
        order.payment_status = "cancelled"
        order.save(update_fields=["payment_status", "updated_at"])
        OrderStatusChange.objects.create(
            order=order,
            field="payment_status",
            from_state=payment_previous,
            to_state="cancelled",
            actor=actor,
            note="Pedido cancelado.",
        )
    order.fulfillment_status = "cancelled"
    order.save(update_fields=["fulfillment_status", "updated_at"])
    change = OrderStatusChange.objects.create(
        order=order,
        field="fulfillment_status",
        from_state=previous,
        to_state="cancelled",
        actor=actor,
        note=reason
        + ("\nCorreo al cliente encolado." if notify else "\nSin notificar al cliente."),
    )
    if order.payment_status == "approved":
        open_incident(order, OrderIncident.Kind.REFUND_PENDING, actor=actor)
    if notify and order.customer_email.strip():
        events._notify(
            order.pk,
            "order_cancelled",
            event_key=f"status:{change.pk}",
            audience="customer",
            metadata={
                "cancellation_reason": reason if include_reason else "",
                "refund_due": bool(order.paid_at or order.payment_status == "approved"),
            },
        )
    events._notify(order.pk, "order_cancelled", event_key=f"status:{change.pk}", audience="serti")
    record(
        "orders.cancelled",
        obj=order,
        actor=actor,
        diff={
            "fulfillment_status": [previous, "cancelled"],
            "reason": ["", reason],
            "include_reason": [False, include_reason],
        },
    )
