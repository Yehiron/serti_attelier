from __future__ import annotations

import hashlib
import hmac
from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.http import HttpRequest

from apps.audit.services import record

from .models import Coupon


def email_digest(email: str) -> str:
    pepper = settings.COUPON_EMAIL_PEPPER
    if not pepper:
        if not settings.DEBUG:
            raise ImproperlyConfigured("COUPON_EMAIL_PEPPER is required")
        pepper = settings.SECRET_KEY
    return hmac.new(pepper.encode(), email.strip().lower().encode(), hashlib.sha256).hexdigest()


@transaction.atomic
def save_coupon(
    coupon: Coupon, *, request: HttpRequest, relations: dict[str, Any] | None = None
) -> None:
    previous = Coupon.objects.select_for_update().filter(pk=coupon.pk).first()
    coupon.code = coupon.code.strip().upper()
    coupon.full_clean()
    coupon.save()
    for name, values in (relations or {}).items():
        getattr(coupon, name).set(values)
    action = (
        "promotions.created"
        if previous is None
        else "promotions.deactivated"
        if previous.is_active and not coupon.is_active
        else "promotions.updated"
    )
    record(
        action,
        actor=request.user,
        obj=coupon,
        request=request,
        diff={"is_active": [previous.is_active if previous else None, coupon.is_active]},
    )


def redeem_coupon() -> None:
    """Phase 6: create a redemption only after payment approval, idempotently."""
    raise NotImplementedError("Payment approval belongs to Phase 6")


@transaction.atomic
def delete_coupon(coupon: Coupon, *, request: HttpRequest) -> None:
    coupon = Coupon.objects.select_for_update().get(pk=coupon.pk)
    record("promotions.deleted", actor=request.user, obj=coupon, request=request)
    coupon.delete()
