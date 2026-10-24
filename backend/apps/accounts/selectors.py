from __future__ import annotations

from typing import Literal, cast

from django.contrib.auth.models import AnonymousUser
from django.db.models import QuerySet
from django_otp.plugins.otp_totp.models import TOTPDevice

from .models import User
from .roles import PROPIETARIO, has_role


def requires_totp(user: User) -> bool:
    return user.is_superuser or has_role(user, PROPIETARIO)


def confirmed_devices(user: User | AnonymousUser) -> QuerySet[TOTPDevice]:
    return cast("QuerySet[TOTPDevice]", TOTPDevice.objects.filter(user=user, confirmed=True))


def pending_second_factor(user: User) -> Literal["setup", "verify"] | None:
    """Single source of the 2FA policy for the dashboard and the staff API."""
    has_device = confirmed_devices(user).exists()
    if requires_totp(user) and not has_device:
        return "setup"
    if has_device and not user.is_verified():  # type: ignore[attr-defined]  # Added by OTPMiddleware.
        return "verify"
    return None


def user_snapshot(user: User) -> dict[str, object]:
    # Explicit fields keep timestamps and password hashes out of the audit payload.
    return {
        field: getattr(user, field)
        for field in (
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
            "is_superuser",
        )
    }
