from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from apps.pricing.services import CouponRules, PricedItem, Quote, quote

NOW = datetime(2026, 10, 24, tzinfo=UTC)
ITEM = PricedItem("A", "Pieza", 10001, category_id=1, collection_ids=frozenset({2}))
COUPON = CouponRules("TEST", "percent", 10)


def calculate(
    items: list[PricedItem], coupon: CouponRules | None = None, certificate: int = 0
) -> Quote:
    return quote(
        items,
        coupon,
        wants_certificate=bool(certificate),
        certificate_cents=certificate,
        email_hash="hash",
        now=NOW,
    )


@pytest.mark.parametrize(
    ("item", "coupon", "total", "reason"),
    [
        (ITEM, None, 10001, None),
        (replace(ITEM, sale_price_cents=8001), None, 8001, None),
        (ITEM, COUPON, 9001, None),
        (replace(ITEM, sale_price_cents=8001), COUPON, 8001, "coupon_not_applicable"),
        (
            replace(ITEM, sale_price_cents=8001),
            replace(COUPON, applies_to_sale_items=True),
            7201,
            None,
        ),
        (ITEM, replace(COUPON, min_subtotal_cents=20000), 10001, "coupon_min_subtotal"),
        (ITEM, replace(COUPON, is_active=False), 10001, "coupon_invalid"),
        (ITEM, replace(COUPON, ends_at=NOW), 10001, "coupon_expired"),
        (ITEM, replace(COUPON, starts_at=NOW + timedelta(seconds=1)), 10001, "coupon_expired"),
        (ITEM, replace(COUPON, max_uses=1, uses=1), 10001, "coupon_exhausted"),
        (ITEM, replace(COUPON, max_uses_per_email=1, email_uses=1), 10001, "coupon_used_by_email"),
        (ITEM, replace(COUPON, kind="fixed", value=20000), 10001, "coupon_not_applicable"),
    ],
)
def test_cases(
    item: PricedItem, coupon: CouponRules | None, total: int, reason: str | None
) -> None:
    result = calculate([item], coupon)
    assert result.total_cents == total
    assert (result.coupon["reason"] if result.coupon else None) == reason
    assert (
        result.total_cents
        == result.subtotal_cents - result.discount_cents + result.certificate_cents
    )


def test_fixed_remainder_and_certificate() -> None:
    items = [replace(ITEM, price_cents=101), replace(ITEM, sku="B", price_cents=202)]
    result = calculate(items, replace(COUPON, kind="fixed", value=100), 50)
    assert [line.discount_cents for line in result.items] == [33, 67]
    assert result.total_cents == 253 and result.shipping_cents == 0
    assert calculate([ITEM], replace(COUPON, kind="fixed", value=20000), 50).total_cents == 50


@pytest.mark.parametrize(
    "restriction", [dict(category_ids=frozenset({1})), dict(collection_ids=frozenset({2}))]
)
def test_mixed_restrictions(restriction: dict[str, frozenset[int]]) -> None:
    other = replace(ITEM, sku="B", category_id=3, collection_ids=frozenset({4}))
    result = calculate(
        [ITEM, other],
        replace(
            COUPON,
            category_ids=restriction.get("category_ids", frozenset()),
            collection_ids=restriction.get("collection_ids", frozenset()),
        ),
    )
    assert [i.discount_cents for i in result.items] == [1000, 0]
