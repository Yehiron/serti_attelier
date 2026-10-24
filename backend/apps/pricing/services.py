from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class PricedItem:
    sku: str
    name: str
    price_cents: int
    sale_price_cents: int | None = None
    category_id: int | None = None
    collection_ids: frozenset[int] = frozenset()

    @property
    def effective_price(self) -> int:
        return self.sale_price_cents if self.sale_price_cents is not None else self.price_cents


@dataclass(frozen=True)
class CouponRules:
    code: str
    kind: str
    value: int
    is_active: bool = True
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    min_subtotal_cents: int = 0
    max_uses: int | None = None
    max_uses_per_email: int | None = None
    uses: int = 0
    email_uses: int = 0
    applies_to_sale_items: bool = False
    category_ids: frozenset[int] = frozenset()
    collection_ids: frozenset[int] = frozenset()


@dataclass(frozen=True)
class QuoteLine:
    sku: str
    name: str
    unit_price_cents: int
    discount_cents: int = 0


@dataclass
class Quote:
    items: list[QuoteLine] = field(default_factory=list)
    subtotal_cents: int = 0
    discount_cents: int = 0
    shipping_cents: int = 0
    certificate_cents: int = 0
    total_cents: int = 0
    currency: str = "COP"
    coupon: dict[str, str | bool | None] | None = None
    payment_channels: tuple[str, ...] = ("wompi", "manual")


def quote(
    items: list[PricedItem],
    coupon: CouponRules | None,
    *,
    wants_certificate: bool,
    certificate_cents: int,
    email_hash: str | None,
    now: datetime,
) -> Quote:
    result = Quote(
        items=[QuoteLine(i.sku, i.name, i.effective_price) for i in items],
        subtotal_cents=sum(i.effective_price for i in items),
        certificate_cents=certificate_cents if wants_certificate else 0,
    )
    if coupon:
        eligible = [
            n
            for n, i in enumerate(items)
            if (i.sale_price_cents is None or coupon.applies_to_sale_items)
            and (
                (not coupon.category_ids and not coupon.collection_ids)
                or i.category_id in coupon.category_ids
                or bool(i.collection_ids & coupon.collection_ids)
            )
        ]
        reason = None
        if not coupon.is_active or coupon.kind not in {"percent", "fixed"}:
            reason = "coupon_invalid"
        elif (coupon.starts_at and now < coupon.starts_at) or (
            coupon.ends_at and now >= coupon.ends_at
        ):
            reason = "coupon_expired"
        elif (coupon.max_uses is not None and coupon.uses >= coupon.max_uses) or (
            email_hash is not None
            and coupon.max_uses_per_email is not None
            and coupon.email_uses >= coupon.max_uses_per_email
        ):
            reason = "coupon_exhausted"
        elif result.subtotal_cents < coupon.min_subtotal_cents:
            reason = "coupon_min_subtotal"
        elif not eligible:
            reason = "coupon_not_applicable"
        discounts = [0] * len(items)
        if reason is None:
            subtotal = sum(items[n].effective_price for n in eligible)
            amount = min(coupon.value, subtotal)
            remaining = amount
            for n in eligible:
                discount = (
                    items[n].effective_price * coupon.value // 100
                    if coupon.kind == "percent"
                    else remaining
                    if n == eligible[-1]
                    else amount * items[n].effective_price // subtotal
                )
                discounts[n] = discount
                remaining -= discount
            if result.subtotal_cents - sum(discounts) + result.certificate_cents <= 0:
                reason = "coupon_not_applicable"
        if reason is None:
            result.items = [
                QuoteLine(i.sku, i.name, i.effective_price, discounts[n])
                for n, i in enumerate(items)
            ]
            result.discount_cents = sum(discounts)
        result.coupon = {"code": coupon.code, "applied": reason is None, "reason": reason}
    result.total_cents = result.subtotal_cents - result.discount_cents + result.certificate_cents
    return result
