import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from apps.inquiries.admin import looks_like_spam
from apps.inquiries.models import ContactInquiry

pytestmark = pytest.mark.django_db


def inquiry(**overrides):
    values = dict(
        name="Ana Pérez",
        email="ana@example.com",
        phone="3001234567",
        topic="piece",
        message="Hola, quiero ver el anillo de esmeralda",
        preferred_channel="email",
        privacy_version=1,
        locale="es",
    )
    values.update(overrides)
    return ContactInquiry.objects.create(**values)


def login_verified(client, user):
    from django_otp import DEVICE_ID_SESSION_KEY
    from django_otp.plugins.otp_totp.models import TOTPDevice

    device = TOTPDevice.objects.create(user=user, confirmed=True)
    client.force_login(user)
    session = client.session
    session[DEVICE_ID_SESSION_KEY] = device.persistent_id
    session.save()


@pytest.fixture
def owner(client):
    user = get_user_model().objects.create_superuser(
        username="owner", email="owner@example.com", password="test"
    )
    login_verified(client, user)
    return client


def test_spam_heuristic():
    assert looks_like_spam("hkjhkjhjhjkhjkhjkhkjhjkhkjhkjhkjhkjh")
    assert looks_like_spam("aaaaaaaaaaaaaaaaaa hola")
    assert looks_like_spam("bcdfgh jklmnp qrstvw")
    assert not looks_like_spam("Hola, quiero ver el anillo de esmeralda")
    assert not looks_like_spam("Hola")


def test_inbox_selection_filters_and_escape(owner):
    first = inquiry(name="Primera", message="<script>alert(1)</script> un mensaje largo")
    second = inquiry(name="Segunda", status="answered", topic="custom")
    url = reverse("admin:inquiries_contactinquiry_changelist")
    response = owner.get(url, {"bandeja": "all", "mensaje": first.pk})
    assert response.status_code == 200
    assert response.context["selected"] == first
    assert (
        b"&lt;script&gt;" in response.content
        and b"<script>alert(1)</script>" not in response.content
    )
    tabs = {tab["label"]: tab["count"] for tab in response.context["msg_tabs"]}
    assert tabs["Sin responder"] == 1 and tabs["Respondidos"] == 1 and tabs["Personalización"] == 1
    assert owner.get(url, {"bandeja": "answered"}).context["selected"] == second


def test_piece_match_and_missing(owner):
    from apps.catalog.models import Piece

    piece = Piece.objects.create(sku="TEST-1", name_es="Anillo", slug_es="anillo", price_cents=100)
    obj = inquiry(piece_sku=piece.sku)
    url = reverse("admin:inquiries_contactinquiry_changelist")
    response = owner.get(url)
    assert response.context["piece"] == piece
    assert b"Anillo" in response.content
    obj.piece_sku = "missing"
    obj.save()
    assert "no indicó referencia" in owner.get(url).content.decode()


def test_status_actions_and_audit(owner):
    from apps.audit.models import AuditLog

    obj = inquiry()
    url = reverse("admin:inquiries_contactinquiry_status", args=[obj.pk]) + "?bandeja=all&q=Ana"
    for status in ("answered", "archived", "new"):
        response = owner.post(url, {"target": status})
        assert (
            response.status_code == 302 and "mensaje=" in response.url and "q=Ana" in response.url
        )
        obj.refresh_from_db()
        assert obj.status == status
        if status == "answered":
            assert obj.answered_at is not None
    assert (
        AuditLog.objects.filter(
            action__in=["inquiries.answered", "inquiries.archived", "inquiries.status_changed"]
        ).count()
        == 3
    )


def test_status_requires_change_permission(client):
    obj = inquiry()
    user = get_user_model().objects.create_user(username="viewer", password="test", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="view_contactinquiry"))
    login_verified(client, user)
    assert (
        client.post(
            reverse("admin:inquiries_contactinquiry_status", args=[obj.pk]), {"target": "answered"}
        ).status_code
        == 403
    )


def test_bulk_actions_remain_available(owner):
    first = inquiry(name="Uno")
    second = inquiry(name="Dos")
    url = reverse("admin:inquiries_contactinquiry_changelist") + "?bandeja=new"
    response = owner.post(
        url, {"action": "mark_answered", "_selected_action": [first.pk, second.pk], "index": "0"}
    )
    assert response.status_code == 302
    assert (
        ContactInquiry.objects.filter(
            pk__in=[first.pk, second.pk], status="answered", answered_at__isnull=False
        ).count()
        == 2
    )
