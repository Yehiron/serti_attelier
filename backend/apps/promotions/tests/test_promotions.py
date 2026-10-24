from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction
from django.test import RequestFactory, override_settings

from apps.audit.models import AuditLog
from apps.promotions.admin import CouponForm
from apps.promotions.models import Coupon
from apps.promotions.services import email_digest, save_coupon

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("kind", "amount", "expected"), [("fixed", "1234.56", 123456), ("percent", "15", 15)]
)
def test_admin_amount(kind: str, amount: str, expected: int) -> None:
    form = CouponForm(
        data={
            "code": " save ",
            "kind": kind,
            "amount": amount,
            "min_subtotal_cents": 0,
            "is_active": True,
        }
    )
    assert form.is_valid(), form.errors
    coupon = form.save(commit=False)
    assert coupon.value == expected and coupon.code == "SAVE"
    request = RequestFactory().post("/")
    request.user = AnonymousUser()
    save_coupon(coupon, request=request)
    coupon.is_active = False
    save_coupon(coupon, request=request)
    assert AuditLog.objects.filter(action="promotions.created").count() == 1
    assert AuditLog.objects.filter(action="promotions.deactivated").count() == 1


@pytest.mark.parametrize(
    ("kind", "amount"), [("percent", "91"), ("percent", "2.5"), ("fixed", "0")]
)
def test_invalid_admin_amount(kind: str, amount: str) -> None:
    form = CouponForm(
        data={"code": "save", "kind": kind, "amount": amount, "min_subtotal_cents": 0}
    )
    assert not form.is_valid()


@pytest.mark.parametrize(
    "values",
    [
        {"kind": "percent", "value": 91},
        {"kind": "fixed", "value": 0},
        {"kind": "percent", "value": 10, "max_uses": 0},
    ],
)
def test_database_constraints(values: dict[str, Any]) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        Coupon.objects.create(code="BAD", **values)


def test_case_insensitive_and_pepper() -> None:
    Coupon.objects.create(code="save", kind="percent", value=10)
    with pytest.raises(IntegrityError), transaction.atomic():
        Coupon.objects.create(code="Save", kind="percent", value=10)
    assert email_digest(" A@example.com ") == email_digest("a@example.com")
    with (
        override_settings(COUPON_EMAIL_PEPPER="", DEBUG=False),
        pytest.raises(ImproperlyConfigured),
    ):
        email_digest("a@example.com")
    with override_settings(COUPON_EMAIL_PEPPER="", DEBUG=True):
        assert len(email_digest("a@example.com")) == 64
