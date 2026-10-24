from __future__ import annotations

from apps.pricing.services import CouponRules

from .models import Coupon

COUNTED_STATUSES = ("pending", "awaiting_manual_payment", "approved")


def coupon_rules(coupon: Coupon, email_hash: str | None) -> CouponRules:
    orders = coupon.order_set.filter(payment_status__in=COUNTED_STATUSES)
    return CouponRules(
        code=coupon.code,
        kind=coupon.kind,
        value=coupon.value,
        is_active=coupon.is_active,
        starts_at=coupon.starts_at,
        ends_at=coupon.ends_at,
        min_subtotal_cents=coupon.min_subtotal_cents,
        max_uses=coupon.max_uses,
        max_uses_per_email=coupon.max_uses_per_email,
        uses=orders.count(),
        email_uses=orders.filter(email_hash=email_hash).count() if email_hash else 0,
        applies_to_sale_items=coupon.applies_to_sale_items,
        category_ids=frozenset(coupon.categories.values_list("pk", flat=True)),
        collection_ids=frozenset(coupon.collections.values_list("pk", flat=True)),
    )
