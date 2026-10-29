import base64
from typing import Any

import pytest
from axes.models import AccessAttempt
from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.accounts.roles import CONTENIDO, OPERACIONES, PROPIETARIO, ROLE_PERMISSIONS, has_role
from apps.accounts.services import sync_roles
from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db
PASSWORD = "Seguro-SERTI-2026"


@pytest.fixture
def staff() -> User:
    return User.objects.create_user(
        username="operador", email="operador@example.com", password=PASSWORD, is_staff=True
    )


def login(
    client: Client, user: User, *, password: str = PASSWORD, ip: str = "198.51.100.42"
) -> Any:
    return client.post(
        reverse("admin:login"),
        {"username": user.username, "password": password, "next": reverse("admin:index")},
        HTTP_X_FORWARDED_FOR=ip,
        REMOTE_ADDR="192.0.2.1",
    )


def code(device: Any) -> str:
    value = totp(
        device.bin_key, step=device.step, t0=device.t0, digits=device.digits, drift=device.drift
    )
    return f"{value:06d}"


def test_roles_exact_idempotent_and_unknown(caplog: pytest.LogCaptureFixture) -> None:
    sync_roles()
    group_ids = list(Group.objects.values_list("pk", flat=True))
    owner = Group.objects.get(name=PROPIETARIO)
    owner.permissions.add(Permission.objects.get(codename="add_auditlog"))
    sync_roles()
    sync_roles()
    assert list(Group.objects.values_list("pk", flat=True)) == group_ids
    for role, expected in ROLE_PERMISSIONS.items():
        actual = {
            f"{p.content_type.app_label}.{p.codename}"
            for p in Group.objects.get(name=role).permissions.select_related("content_type")
        }
        assert actual == expected
    ROLE_PERMISSIONS[CONTENIDO].add("future.view_piece")
    try:
        sync_roles()
        assert "future.view_piece" in caplog.text
        assert (
            not Group.objects.get(name=CONTENIDO)
            .permissions.filter(codename="view_piece", content_type__app_label="future")
            .exists()
        )
    finally:
        ROLE_PERMISSIONS[CONTENIDO].remove("future.view_piece")


def test_argon2() -> None:
    with override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.Argon2PasswordHasher"]):
        user = User(username="hash", email="hash@example.com")
        user.set_password(PASSWORD)
        user.save()
        user.refresh_from_db()
        assert user.password.startswith("argon2$")
        assert user.check_password(PASSWORD)


def test_axes_lockout_and_audit(client: Client, staff: User) -> None:
    for _ in range(5):
        login(client, staff, password="wrong")
    response = login(client, staff)
    assert response.status_code == 429
    assert "Por seguridad bloqueamos temporalmente el acceso" in response.content.decode()
    assert "_auth_user_id" not in client.session
    assert AuditLog.objects.filter(action="auth.locked_out", ip="198.51.100.42").exists()
    # The key is the combination, not username alone or IP alone.
    assert login(client, staff, ip="198.51.100.43").status_code == 302


def test_axes_success_resets(client: Client, staff: User) -> None:
    for _ in range(4):
        login(client, staff, password="wrong")
    assert AccessAttempt.objects.filter(username=staff.username).exists()
    assert login(client, staff).status_code == 302
    assert not AccessAttempt.objects.filter(username=staff.username).exists()
    client.logout()
    for _ in range(4):
        assert login(client, staff, password="wrong").status_code == 200
    assert login(client, staff).status_code == 302


@pytest.mark.parametrize("superuser", [False, True])
def test_required_user_redirected_to_setup(client: Client, staff: User, superuser: bool) -> None:
    if superuser:
        staff.is_superuser = True
        staff.save()
    else:
        staff.groups.add(Group.objects.get(name=PROPIETARIO))
        assert has_role(staff, PROPIETARIO)
    login(client, staff)
    response = client.get(reverse("admin:index"))
    assert response.status_code == 302
    assert response.headers["Location"].startswith(reverse("admin-2fa-setup"))
    # Model endpoints are covered too.
    assert (
        client.get(reverse("admin:accounts_user_changelist"))
        .headers["Location"]
        .startswith(reverse("admin-2fa-setup"))
    )


def test_setup_confirms_reuses_device_and_grants_access(client: Client, staff: User) -> None:
    staff.groups.add(Group.objects.get(name=PROPIETARIO))
    login(client, staff)
    url = reverse("admin-2fa-setup")
    response = client.get(url)
    assert response.status_code == 200
    device = TOTPDevice.objects.get(user=staff)
    assert not device.confirmed
    assert base64.b32encode(device.bin_key).decode() in response.content.decode()
    assert "<svg" in response.content.decode()
    assert "issuer=SERTI" in device.config_url
    client.get(url)
    assert TOTPDevice.objects.filter(user=staff).count() == 1
    response = client.post(url, {"token": code(device)})
    assert response.status_code == 302
    device.refresh_from_db()
    assert device.confirmed
    assert client.session[DEVICE_ID_SESSION_KEY] == device.persistent_id
    assert client.get(reverse("admin:index")).status_code == 200
    assert AuditLog.objects.filter(action="auth.2fa_enabled", actor=staff).count() == 1


def test_staff_device_requires_verification_and_rejects_wrong_code(
    client: Client, staff: User
) -> None:
    device = TOTPDevice.objects.create(user=staff, confirmed=True)
    login(client, staff)
    response = client.get(reverse("admin:index"))
    assert response.headers["Location"].startswith(reverse("admin-2fa-verify"))
    response = client.post(reverse("admin-2fa-verify"), {"token": "bad"})
    assert response.status_code == 200
    assert "Código inválido" in response.content.decode()
    assert DEVICE_ID_SESSION_KEY not in client.session
    assert AuditLog.objects.filter(action="auth.2fa_failed", actor=staff).exists()
    device.refresh_from_db()
    assert device.throttling_failure_count == 1
    # Built-in exponential throttling is enforced even for a correct token immediately afterward.
    client.post(reverse("admin-2fa-verify"), {"token": code(device)})
    assert DEVICE_ID_SESSION_KEY not in client.session


@pytest.mark.parametrize("target", ["https://evil.example/", "//evil.example/", "/dashboard/"])
def test_verify_safe_next(client: Client, staff: User, target: str) -> None:
    device = TOTPDevice.objects.create(user=staff, confirmed=True)
    login(client, staff)
    response = client.post(reverse("admin-2fa-verify"), {"token": code(device), "next": target})
    assert response.status_code == 302
    assert response.headers["Location"] == reverse("admin:index")
    assert client.get(reverse("admin:index")).status_code == 200


def test_verified_session_invalidated_when_device_removed(client: Client, staff: User) -> None:
    staff.groups.add(Group.objects.get(name=PROPIETARIO))
    device = TOTPDevice.objects.create(user=staff, confirmed=True)
    login(client, staff)
    client.post(reverse("admin-2fa-verify"), {"token": code(device)})
    device.delete()
    assert (
        client.get(reverse("admin:index"))
        .headers["Location"]
        .startswith(reverse("admin-2fa-setup"))
    )


def test_operations_without_device_and_session_rotation(client: Client, staff: User) -> None:
    staff.groups.add(Group.objects.get(name=OPERACIONES))
    session = client.session
    session["test"] = "anonymous-session"
    session.save()
    old_key = session.session_key
    login(client, staff)
    assert old_key != client.session.session_key
    assert client.get(reverse("admin:index")).status_code == 200
    assert settings.SESSION_COOKIE_AGE == 1800
    assert settings.SESSION_SAVE_EVERY_REQUEST
    assert client.session.get_expiry_age() <= 1800


def test_password_reset_private_response_and_email(client: Client, staff: User) -> None:
    url = reverse("admin_password_reset")
    assert "¿Olvidaste tu contraseña?" in client.get(reverse("admin:login")).content.decode()
    known = client.post(url, {"email": staff.email})
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [staff.email]
    unknown = client.post(url, {"email": "unknown@example.com"})
    assert len(mail.outbox) == 1
    assert (known.status_code, known.headers["Location"], known.content) == (
        unknown.status_code,
        unknown.headers["Location"],
        unknown.content,
    )
    assert client.get(known.headers["Location"]).status_code == 200
    assert AuditLog.objects.filter(action="auth.password_reset_requested").count() == 2


def test_password_reset_completion(client: Client, staff: User) -> None:
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    url = reverse(
        "password_reset_confirm",
        kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(staff.pk)),
            "token": default_token_generator.make_token(staff),
        },
    )
    response = client.get(url)
    response = client.post(
        response.headers["Location"],
        {"new_password1": PASSWORD + "new", "new_password2": PASSWORD + "new"},
    )
    assert response.status_code == 302
    assert client.get(response.headers["Location"]).status_code == 200
    staff.refresh_from_db()
    assert staff.check_password(PASSWORD + "new")
    event = AuditLog.objects.get(action="auth.password_changed")
    assert event.diff == {}


def test_custom_admin_prefix(client: Client, staff: User) -> None:
    # Middleware derives the prefix from settings rather than hardcoding dashboard.
    from django.http import HttpResponse

    from apps.accounts.middleware import AdminAccessMiddleware

    staff.is_superuser = True
    request = RequestFactory().get("/private-control/accounts/user/")
    request.user = staff
    with override_settings(ADMIN_URL="private-control/"):
        response = AdminAccessMiddleware(lambda request: HttpResponse())(request)
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/private-control/2fa/setup/")


def test_totp_replay_rejected(client: Client, staff: User) -> None:
    device = TOTPDevice.objects.create(user=staff, confirmed=True)
    login(client, staff)
    token = code(device)
    assert client.post(reverse("admin-2fa-verify"), {"token": token}).status_code == 302
    session = client.session
    del session[DEVICE_ID_SESSION_KEY]
    session.save()
    assert client.post(reverse("admin-2fa-verify"), {"token": token}).status_code == 200
    assert DEVICE_ID_SESSION_KEY not in client.session


@pytest.mark.parametrize(
    "token", ["", "12", "\x00", "\uff11\uff12\uff13\uff14\uff15\uff16", "x" * 200]
)
def test_malformed_totp_is_throttled_and_audited(client: Client, staff: User, token: str) -> None:
    device = TOTPDevice.objects.create(user=staff, confirmed=True)
    login(client, staff)
    response = client.post(reverse("admin-2fa-verify"), {"token": token})
    assert response.status_code == 200
    device.refresh_from_db()
    assert device.throttling_failure_count == 1
    assert AuditLog.objects.filter(action="auth.2fa_failed", actor=staff).count() == 1


def test_setup_requires_active_staff(client: Client, staff: User) -> None:
    assert client.get(reverse("admin-2fa-setup")).status_code == 302
    staff.is_staff = False
    staff.save()
    client.force_login(staff)
    assert client.get(reverse("admin-2fa-setup")).status_code == 302
    assert not TOTPDevice.objects.filter(user=staff).exists()


def test_totp_views_enforce_csrf(staff: User) -> None:
    device = TOTPDevice.objects.create(user=staff, confirmed=True)
    client = Client(enforce_csrf_checks=True)
    client.force_login(staff)
    assert client.post(reverse("admin-2fa-verify"), {"token": code(device)}).status_code == 403


def test_unverified_session_does_not_see_dashboard_sections(client: Client, staff: User) -> None:
    staff.is_superuser = True
    staff.save()
    TOTPDevice.objects.create(user=staff, confirmed=True)
    login(client, staff)
    page = client.get(reverse("admin-2fa-verify")).content.decode()
    assert "Verificar acceso" in page
    assert reverse("admin:catalog_piece_changelist") not in page
