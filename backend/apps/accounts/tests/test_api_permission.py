from collections.abc import Callable

import pytest
from django.contrib.auth.models import AnonymousUser, Group
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.roles import OPERACIONES, PROPIETARIO
from apps.accounts.services import sync_roles

pytestmark = pytest.mark.django_db


class StaffProbe(APIView):
    """Uses the project's default permission, like any future staff endpoint."""

    def get(self, request: Request) -> Response:
        return Response({"ok": True})


def call(user: User | AnonymousUser, *, verified: bool = False) -> int:
    if isinstance(user, User):
        # OTPMiddleware normally attaches this; the request factory skips middleware.
        is_verified: Callable[[], bool] = lambda: verified  # noqa: E731
        user.is_verified = is_verified
    request = APIRequestFactory().get("/probe")
    force_authenticate(request, user=user)
    return int(StaffProbe.as_view()(request).status_code)


def staff_user(username: str, role: str | None = None, *, superuser: bool = False) -> User:
    sync_roles()
    user = User.objects.create_user(
        username, f"{username}@example.com", "x", is_staff=True, is_superuser=superuser
    )
    if role:
        user.groups.add(Group.objects.get(name=role))
    return user


def test_anonymous_and_non_staff_are_rejected() -> None:
    assert call(AnonymousUser()) in {401, 403}
    assert call(User.objects.create_user("cliente", "c@example.com", "x")) == 403


def test_owner_needs_second_factor_on_the_api_too() -> None:
    owner = staff_user("duena", PROPIETARIO)
    assert call(owner) == 403  # no device yet: setup pending
    TOTPDevice.objects.create(user=owner, confirmed=True)
    assert call(owner, verified=False) == 403  # password only
    assert call(owner, verified=True) == 200


def test_superuser_without_device_is_rejected() -> None:
    assert call(staff_user("root", superuser=True)) == 403


def test_staff_with_device_must_verify() -> None:
    operator = staff_user("operador", OPERACIONES)
    assert call(operator) == 200  # no requirement, no device
    TOTPDevice.objects.create(user=operator, confirmed=True)
    assert call(operator, verified=False) == 403
    assert call(operator, verified=True) == 200
