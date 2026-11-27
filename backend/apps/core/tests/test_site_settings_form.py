from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.core.selectors import get_solo

pytestmark = pytest.mark.django_db


def login(client, user):
    # The dashboard requires a verified second factor, like real staff sessions.
    device, _ = TOTPDevice.objects.get_or_create(user=user, defaults={"confirmed": True})
    client.force_login(user)
    session = client.session
    session[DEVICE_ID_SESSION_KEY] = device.persistent_id
    session.save()


@pytest.fixture
def owner(client):
    user = User.objects.create_superuser(
        username="settings-owner", email="owner@example.com", password="password"
    )
    login(client, user)
    return user


def form_data(client):
    response = client.get(reverse("admin:core_sitesettings_change", args=[get_solo().pk]))
    form = response.context["adminform"].form
    data = {}
    for name, field in form.fields.items():
        value = form[name].value()
        if getattr(field.widget, "input_type", "") == "checkbox":
            if value:
                data[name] = "on"
        else:
            data[name] = "" if value is None else str(value)
    data["_continue"] = "1"
    return data


def test_redirect_and_sections(client, owner):
    response = client.get(reverse("admin:core_sitesettings_changelist"))
    assert response.status_code == 302
    assert response.url == reverse("admin:core_sitesettings_change", args=[get_solo().pk])
    response = client.get(response.url)
    for section in (
        "Contacto y redes",
        "Mensajes de WhatsApp",
        "Pagos y reservas",
        "Google (SEO)",
        "Horario y zona",
    ):
        assert section in response.content.decode()


def test_save_and_audit_redaction(client, owner):
    data = form_data(client)
    data.update(
        whatsapp_number="573027821575",
        instagram_url="https://instagram.com/qa.serti",
        whatsapp_sold_es="Consulta {name} {sku} {url}",
    )
    response = client.post(reverse("admin:core_sitesettings_change", args=[1]), data)
    assert response.status_code == 302
    obj = get_solo()
    assert obj.whatsapp_number == data["whatsapp_number"]
    assert obj.instagram_url == data["instagram_url"]
    assert obj.whatsapp_sold_es == data["whatsapp_sold_es"]
    diff = AuditLog.objects.filter(action="core.settings_updated").first().diff
    assert diff["whatsapp_number"][1] == data["whatsapp_number"]
    assert diff["whatsapp_sold_es"] == ["[redactado]", "[redactado]"]
    assert (
        "Parece de pruebas"
        in client.get(reverse("admin:core_sitesettings_change", args=[1])).content.decode()
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("whatsapp_sold_es", "{precio}"),
        ("whatsapp_number", "+573001234567"),
        ("whatsapp_number", "letras"),
    ],
)
def test_invalid_fields_do_not_save(client, owner, field, value):
    obj = get_solo()
    before = getattr(obj, field)
    data = form_data(client)
    data[field] = value
    data["instagram_url"] = "https://instagram.com/changed"
    response = client.post(reverse("admin:core_sitesettings_change", args=[1]), data)
    assert response.status_code == 200
    assert field in response.context["adminform"].form.errors
    obj.refresh_from_db()
    assert getattr(obj, field) == before
    assert obj.instagram_url != data["instagram_url"]
    assert not AuditLog.objects.filter(action="core.settings_updated").exists()


def test_permissions(client, owner):
    data = form_data(client)
    user = User.objects.create_user(username="viewer", email="viewer@example.com", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="view_sitesettings"))
    login(client, user)
    url = reverse("admin:core_sitesettings_change", args=[1])
    assert client.get(url).status_code == 200
    assert client.post(url, data).status_code == 403
    user.user_permissions.add(Permission.objects.get(codename="change_sitesettings"))
    user = User.objects.get(pk=user.pk)
    login(client, user)
    assert client.post(url, data).status_code == 403
    user.user_permissions.clear()
    user = User.objects.get(pk=user.pk)
    login(client, user)
    assert client.get(reverse("admin:core_sitesettings_changelist")).status_code == 403
    assert client.get(url).status_code == 403
