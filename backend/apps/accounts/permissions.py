from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from .models import User
from .selectors import pending_second_factor


class IsVerifiedStaff(BasePermission):
    """Default API permission: staff who completed the same 2FA policy as the dashboard.

    Session authentication is shared with the admin, so without this a staff user who
    only entered a password could call staff API endpoints before verifying TOTP.
    """

    def has_permission(self, request: Request, view: Any) -> bool:
        user = request.user
        return (
            isinstance(user, User)
            and user.is_active
            and user.is_staff
            and pending_second_factor(user) is None
        )
