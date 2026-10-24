from typing import Any

import pytest
from django.contrib import admin
from django.contrib.auth.models import AnonymousUser
from django.test import Client, RequestFactory
from django.urls import reverse
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.audit.diff import compute_diff
from apps.audit.models import AuditLog
from apps.audit.services import record
from apps.core.http import client_ip

pytestmark = pytest.mark.django_db


def test_sensitive_diff_fields() -> None:
    old: dict[str, object] = dict.fromkeys(
        ["password", "Password", "api_key", "secret", "access_token", "email", "ignored"], "old"
    )
    new: dict[str, object] = dict.fromkeys(old, "new")
    assert compute_diff(old, new, exclude=("ignored",)) == {"email": ["old", "new"]}
    assert compute_diff({"name": "a"}, {"name": "a"}) == {}
    assert compute_diff({}, {"name": "new"}) == {"name": [None, "new"]}


@pytest.mark.parametrize(
    "forwarded,remote,expected",
    [
        ("198.51.100.2", "192.0.2.1", "198.51.100.2"),
        ("203.0.113.9, 198.51.100.2", "192.0.2.1", "198.51.100.2"),
        ("", "192.0.2.1", "192.0.2.1"),
        ("invalid", "192.0.2.1", None),
        ("2001:db8::1", "192.0.2.1", "2001:db8::1"),
    ],
)
def test_client_ip(forwarded: str, remote: str, expected: str | None) -> None:
    request = RequestFactory().get("/", HTTP_X_FORWARDED_FOR=forwarded, REMOTE_ADDR=remote)
    assert client_ip(request) == expected


def test_auth_events(client: Client) -> None:
    user = User.objects.create_user(
        username="audit", email="audit@example.com", password="good", is_staff=True
    )
    url = reverse("admin:login")
    headers: dict[str, Any] = {
        "HTTP_X_FORWARDED_FOR": "203.0.113.99, 198.51.100.42",
        "HTTP_USER_AGENT": "x" * 400,
    }
    client.post(url, {"username": user.username, "password": "never-record-this"}, **headers)
    client.post(url, {"username": user.username, "password": "good"}, **headers)
    client.post(reverse("admin:logout"), **headers)
    events = AuditLog.objects.filter(action__in=["auth.login", "auth.login_failed", "auth.logout"])
    assert events.count() == 3
    assert set(events.values_list("ip", flat=True)) == {"198.51.100.42"}
    assert all(len(event.user_agent) == 300 for event in events)
    failure = events.get(action="auth.login_failed")
    assert failure.diff == {"username": [None, "audit"]}
    assert "never-record-this" not in str(list(events.values()))


@pytest.fixture
def owner_client(client: Client) -> Client:
    owner = User.objects.create_superuser("owner", "owner@example.com", "good")
    device = TOTPDevice.objects.create(user=owner, confirmed=True)
    client.force_login(owner)
    session = client.session
    session[DEVICE_ID_SESSION_KEY] = device.persistent_id
    session.save()
    return client


def test_admin_user_update_diff_and_membership(owner_client: Client) -> None:
    from django.contrib.auth.models import Group

    from apps.accounts.roles import OPERACIONES

    user = User.objects.create_user("target", "old@example.com", "old-password")
    response = owner_client.post(
        reverse("admin:accounts_user_change", args=[user.pk]),
        {
            "username": user.username,
            "email": "new@example.com",
            "first_name": "Nuevo",
            "last_name": "",
            "is_active": "on",
            "is_staff": "on",
            "groups": [Group.objects.get(name=OPERACIONES).pk],
            "date_joined_0": "2026-10-23",
            "date_joined_1": "12:00:00",
        },
    )
    assert response.status_code == 302
    event = AuditLog.objects.get(action="accounts.user_updated", object_id=str(user.pk))
    assert event.diff["email"] == ["old@example.com", "new@example.com"]
    assert all("password" not in key for key in event.diff)
    assert AuditLog.objects.filter(
        action="accounts.access_changed", object_id=str(user.pk)
    ).exists()


def test_admin_password_change(owner_client: Client) -> None:
    user = User.objects.create_user("target", "target@example.com", "old-password")
    response = owner_client.post(
        reverse("admin:auth_user_password_change", args=[user.pk]),
        {
            "password1": "New-Secure-SERTI-2026",
            "password2": "New-Secure-SERTI-2026",
            "usable_password": "true",
        },
    )
    assert response.status_code == 302
    assert AuditLog.objects.get(action="auth.password_changed").diff == {}


def test_immutable_rows() -> None:
    event = record("system.test")
    event.action = "tampered"
    with pytest.raises(ValueError):
        event.save()
    with pytest.raises(ValueError):
        event.delete()
    with pytest.raises(ValueError):
        AuditLog.objects.filter(pk=event.pk).update(action="tampered")
    with pytest.raises(ValueError):
        AuditLog.objects.filter(pk=event.pk).delete()
    event.refresh_from_db()
    assert event.action == "system.test"


def test_actor_deletion_preserves_history() -> None:
    user = User.objects.create_user("deleted", "deleted@example.com")
    event = record("system.test", actor=user, obj=user)
    user.delete()
    event.refresh_from_db()
    assert event.actor is None
    assert event.actor_repr == "deleted"
    assert event.object_repr == "deleted"


def test_audit_admin_read_only(owner_client: Client) -> None:
    event = record("system.test")
    model_admin = admin.site._registry[AuditLog]
    request = RequestFactory().get("/")
    request.user = User.objects.get(username="owner")
    assert model_admin.has_view_permission(request)
    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_change_permission(request, event)
    assert not model_admin.has_delete_permission(request, event)
    assert owner_client.get(reverse("admin:audit_auditlog_changelist")).status_code == 200
    assert owner_client.post(reverse("admin:audit_auditlog_add")).status_code == 403
    assert (
        owner_client.post(reverse("admin:audit_auditlog_change", args=[event.pk])).status_code
        == 403
    )
    assert (
        owner_client.post(reverse("admin:audit_auditlog_delete", args=[event.pk])).status_code
        == 403
    )
    request.user = AnonymousUser()
    assert not model_admin.has_view_permission(request)


def test_admin_own_password_change(owner_client: Client) -> None:
    response = owner_client.post(
        reverse("admin:password_change"),
        {
            "old_password": "good",
            "new_password1": "New-Secure-SERTI-2026",
            "new_password2": "New-Secure-SERTI-2026",
        },
    )
    assert response.status_code == 302
    assert owner_client.get(reverse("admin:index")).status_code == 200
    event = AuditLog.objects.get(action="auth.password_changed")
    assert event.actor_repr == "owner"
    assert event.diff == {}


def test_device_removal_audited(owner_client: Client) -> None:
    device = TOTPDevice.objects.create(user=User.objects.get(username="owner"), confirmed=True)
    response = owner_client.post(
        reverse("admin:otp_totp_totpdevice_delete", args=[device.pk]), {"post": "yes"}
    )
    assert response.status_code == 302
    assert not TOTPDevice.objects.filter(pk=device.pk).exists()
    assert AuditLog.objects.filter(action="auth.2fa_removed", object_id=str(device.pk)).exists()


def test_new_instance_cannot_overwrite_audit() -> None:
    event = record("system.test")
    with pytest.raises(ValueError):
        AuditLog(pk=event.pk, action="tampered").save()


def test_role_permission_change_is_audited(owner_client: Client) -> None:
    from django.contrib.auth.models import Group, Permission

    group = Group.objects.create(name="Temporal")
    permission = Permission.objects.get(codename="view_auditlog")
    response = owner_client.post(
        reverse("admin:auth_group_change", args=[group.pk]),
        {"name": group.name, "permissions": [permission.pk]},
    )
    assert response.status_code == 302
    event = AuditLog.objects.get(
        action="accounts.role_permissions_changed", object_id=str(group.pk)
    )
    assert event.diff == {"permissions": [[], ["audit.view_auditlog"]]}


def test_direct_user_permission_grant_is_audited(owner_client: Client) -> None:
    from django.contrib.auth.models import Permission

    user = User.objects.create_user("directo", "directo@example.com", "x", is_staff=True)
    permission = Permission.objects.get(codename="view_auditlog")
    response = owner_client.post(
        reverse("admin:accounts_user_change", args=[user.pk]),
        {
            "username": user.username,
            "email": user.email,
            "is_active": "on",
            "is_staff": "on",
            "user_permissions": [permission.pk],
            "date_joined_0": "2026-10-23",
            "date_joined_1": "12:00:00",
        },
    )
    assert response.status_code == 302
    event = AuditLog.objects.get(action="accounts.access_changed", object_id=str(user.pk))
    assert event.diff == {"user_permissions": [[], ["audit.view_auditlog"]]}
