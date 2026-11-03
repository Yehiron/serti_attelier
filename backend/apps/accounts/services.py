from __future__ import annotations

import logging
from collections.abc import Callable
from typing import cast

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpRequest
from django_otp import login as otp_login
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.audit.diff import compute_diff
from apps.audit.services import record

from .models import User
from .roles import ROLE_PERMISSIONS
from .selectors import user_snapshot

logger = logging.getLogger(__name__)


@transaction.atomic
def sync_roles(*, using: str = "default") -> None:
    # post_migrate handlers run in app order. Create permissions for every app now,
    # including those whose own post_migrate callback has not run yet.
    from django.apps import apps
    from django.contrib.auth.management import create_permissions

    for config in apps.get_app_configs():
        create_permissions(config, verbosity=0, using=using)
    for name, codenames in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.using(using).get_or_create(name=name)
        permissions = []
        for qualified in sorted(codenames):
            label, codename = qualified.split(".", 1)
            permission = (
                Permission.objects.using(using)
                .filter(content_type__app_label=label, codename=codename)
                .first()
            )
            if permission is None:
                logger.warning("Unknown role permission: %s", qualified)
            else:
                permissions.append(permission)
        group.permissions.set(permissions)


@transaction.atomic
def setup_device(user: User | AnonymousUser) -> TOTPDevice:
    # Serialize concurrent setup requests on the user; never create multiple pending devices.
    if not isinstance(user, User) or not user.is_staff:
        raise PermissionDenied
    User.objects.select_for_update().get(pk=user.pk)
    device = TOTPDevice.objects.filter(user=user, confirmed=False).order_by("pk").first()
    return cast(
        TOTPDevice, device or TOTPDevice.objects.create(user=user, name="SERTI", confirmed=False)
    )


@transaction.atomic
def verify_device(request: HttpRequest, device_id: int, token: str, *, setup: bool) -> bool:
    device = TOTPDevice.objects.select_for_update().get(pk=device_id, user=request.user)
    if bool(device.confirmed) == setup:
        return False
    # Let the device process malformed tokens too, so its throttle covers every failure.
    valid_format = len(token) == 6 and token.isascii() and token.isdigit()
    valid = device.verify_token(token if valid_format else "invalid")
    if not valid:
        record("auth.2fa_failed", actor=request.user, request=request)
        return False
    if setup:
        device.confirmed = True
        device.save(update_fields=["confirmed"])
        record("auth.2fa_enabled", actor=request.user, obj=device, request=request)
    otp_login(request, device)
    request.session.cycle_key()
    return True


@transaction.atomic
def save_user(user: User, *, request: HttpRequest) -> None:
    old = User.objects.filter(pk=user.pk).first() if user.pk else None
    diff = compute_diff(user_snapshot(old) if old else {}, user_snapshot(user))
    user.save()
    record(
        "accounts.user_updated" if old else "accounts.user_created",
        actor=request.user,
        obj=user,
        diff=diff,
        request=request,
    )
    if old and old.password != user.password:
        record("auth.password_changed", actor=request.user, obj=user, request=request)


@transaction.atomic
def delete_user(user: User, *, request: HttpRequest) -> None:
    record("accounts.user_deleted", actor=request.user, obj=user, request=request)
    user.delete()


def access_snapshot(user: User) -> dict[str, list[str]]:
    """Group names and direct permissions: the two ways the admin grants privileges."""
    return {
        "groups": sorted(user.groups.values_list("name", flat=True)),
        "user_permissions": sorted(
            f"{app}.{codename}"
            for app, codename in user.user_permissions.values_list(
                "content_type__app_label", "codename"
            )
        ),
    }


@transaction.atomic
def record_access_changes(user: User, old: dict[str, list[str]], *, request: HttpRequest) -> None:
    diff = compute_diff(old, access_snapshot(user))
    if diff:
        record("accounts.access_changed", actor=request.user, obj=user, diff=diff, request=request)


def group_permissions(group: Group) -> list[str]:
    return sorted(
        f"{app}.{codename}"
        for app, codename in group.permissions.values_list("content_type__app_label", "codename")
    )


@transaction.atomic
def save_related_group(group: Group, save: Callable[[], None], *, request: HttpRequest) -> None:
    old = group_permissions(group) if group.pk else []
    save()
    new = group_permissions(group)
    if old != new:
        record(
            "accounts.role_permissions_changed",
            actor=request.user,
            obj=group,
            diff={"permissions": [old, new]},
            request=request,
        )


@transaction.atomic
def remove_device(device: TOTPDevice, *, request: HttpRequest) -> None:
    record("auth.2fa_removed", actor=request.user, obj=device, request=request)
    device.delete()


@transaction.atomic
def change_password(
    form: SetPasswordForm[User], *, request: HttpRequest, refresh_session: bool = False
) -> None:
    user = form.save()
    actor = request.user if request.user.is_authenticated else user
    record("auth.password_changed", actor=actor, obj=user, request=request)
    if refresh_session:
        update_session_auth_hash(request, user)


@transaction.atomic
def save_related_user(user: User, save: Callable[[], None], *, request: HttpRequest) -> None:
    old = access_snapshot(user)
    save()
    record_access_changes(user, old, request=request)


@transaction.atomic
def assign_team_role(user: User, role: str, *, request: HttpRequest) -> None:
    """Assign a managed role without allowing callers to grant their own missing privileges."""
    if role not in ROLE_PERMISSIONS:
        raise PermissionDenied
    if not request.user.is_superuser:
        if user.is_superuser or not request.user.has_perm("accounts.change_user"):
            raise PermissionDenied
        if not all(request.user.has_perm(permission) for permission in ROLE_PERMISSIONS[role]):
            raise PermissionDenied
    old = access_snapshot(user)
    sync_roles()
    user.groups.set([Group.objects.get(name=role)])
    user.user_permissions.clear()
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    record_access_changes(user, old, request=request)
