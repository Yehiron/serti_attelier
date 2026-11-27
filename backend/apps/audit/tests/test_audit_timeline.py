import pytest
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory
from django.urls import reverse
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.audit.admin import rows_for
from apps.audit.models import AuditLog
from apps.audit.presentation import changes, describe

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff(client):
    user = User.objects.create_superuser("auditor", "audit@example.com", "password")
    device = TOTPDevice.objects.create(user=user, confirmed=True)
    client.force_login(user)
    session = client.session
    session[DEVICE_ID_SESSION_KEY] = device.persistent_id
    session.save()
    return client


def event(action="catalog.piece_updated", **kwargs):
    return AuditLog.objects.create(action=action, **kwargs)


def test_descriptions():
    assert (
        describe(event(actor_repr="Ana", object_repr="Anillo")) == "Ana actualizó la pieza Anillo"
    )
    assert "creó el pedido" in describe(event("orders.created", actor_repr="Ana"))
    assert (
        describe(event("payments.approved", object_repr="123"))
        == "Sistema aprobó el pago del pedido 123"
    )
    assert "Acción registrada:" in describe(event("desconocida.algo"))
    assert describe(event(actor_repr="e2e-test")).startswith("Prueba automática")


def test_changes():
    entry = event(
        diff={
            "password": ["[redactado]", ""],
            "price_cents": [None, 120000000],
            "enabled": [False, True],
            "id": [1, 2],
            "updated_at": [1, 2],
        }
    )
    result = changes(entry)
    assert len(result) == 3
    assert result[0]["before"] == "(oculto por seguridad)"
    assert result[0]["after"] == "Vacío"
    assert result[1]["after"] == "$ 1.200.000"
    assert (result[2]["before"], result[2]["after"]) == ("No", "Sí")


def test_filters_and_test_visibility(staff):
    event("orders.created", actor_repr="Ana", object_repr="Pedido visible")
    event("auth.login", actor_repr="Ana")
    event("catalog.piece_updated", actor_repr="e2e-123", object_repr="Pieza E2E prueba")
    url = reverse("admin:audit_auditlog_changelist")
    response = staff.get(url)
    assert response.status_code == 200
    assert "Pieza E2E prueba" not in response.content.decode()
    assert "Pieza E2E prueba" in staff.get(url, {"pruebas": "mostrar"}).content.decode()
    assert (
        "Pedido visible"
        in staff.get(
            url, {"modulo": "Pedidos", "periodo": "hoy", "persona": "Ana"}
        ).content.decode()
    )
    assert "Pedido visible" not in staff.get(url, {"seguridad": "1"}).content.decode()
    assert staff.get(url, {"periodo": "7"}).status_code == 200
    assert staff.get(url, {"periodo": "30"}).status_code == 200


def test_grouping_and_object_links(staff):
    user = User.objects.create_user("objetivo", password="x")
    ct = ContentType.objects.get_for_model(User)
    event("accounts.user_updated", content_type=ct, object_id=str(user.pk), object_repr="objetivo")
    event("accounts.user_deleted", content_type=ct, object_id="999999", object_repr="ausente")
    response = staff.get(reverse("admin:audit_auditlog_changelist"))
    assert "Hoy" in response.content.decode()
    assert reverse("admin:accounts_user_change", args=[user.pk]) in response.content.decode()
    assert "eliminado" in response.content.decode()


def test_queries_do_not_grow_per_row(django_assert_num_queries):
    user = User.objects.create_user("objeto", password="x")
    ct = ContentType.objects.get_for_model(User)
    entries = [event(content_type=ct, object_id=str(user.pk), actor=user) for _ in range(50)]
    with django_assert_num_queries(1):
        rows_for(entries[:10])
    with django_assert_num_queries(1):
        rows_for(entries)


def test_permission_and_read_only(client):
    user = User.objects.create_user("sinpermiso", password="x", is_staff=True)
    device = TOTPDevice.objects.create(user=user, confirmed=True)
    client.force_login(user)
    session = client.session
    session[DEVICE_ID_SESSION_KEY] = device.persistent_id
    session.save()
    assert client.get(reverse("admin:audit_auditlog_changelist")).status_code == 403
    user.user_permissions.add(Permission.objects.get(codename="view_auditlog"))
    request = RequestFactory().get("/")
    request.user = User.objects.get(pk=user.pk)
    model_admin = admin.site._registry[AuditLog]
    assert model_admin.has_view_permission(request)
    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_change_permission(request)
    assert not model_admin.has_delete_permission(request)


def test_changes_skip_rows_that_read_the_same():
    from types import SimpleNamespace

    from apps.audit.presentation import changes

    entry = SimpleNamespace(
        content_type_id=None,
        diff={"description_en": ["", None], "name": ["Aretes", "Aros"]},
    )
    assert [row["label"] for row in changes(entry)] == ["Name"]
