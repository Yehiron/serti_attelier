from unittest.mock import patch

import pytest
from django.contrib import admin
from django.contrib.auth.models import Group
from django.core import mail
from django.core.cache import cache
from django.test import RequestFactory
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.services import sync_roles
from apps.cms.models import Page, PageRevision
from apps.core.selectors import get_solo
from apps.inquiries.models import ContactInquiry
from apps.inquiries.tasks import notify_atelier, send_acknowledgement


@pytest.fixture
def payload(db):
    page = Page.objects.get(kind="privacy")
    page.status = "published"
    page.save(update_fields=["status"])
    PageRevision.objects.create(page=page, version=3, snapshot={})
    cache.clear()
    return {
        "name": "Ana",
        "email": "ana@example.com",
        "phone": "573001234567",
        "topic": "piece",
        "piece_sku": "ABC",
        "message": "Quiero saber más sobre esta pieza.",
        "preferred_channel": "email",
        "accepted_privacy_version": 3,
        "locale": "en",
        "elapsed_ms": 4000,
        "website": "",
    }


@pytest.mark.django_db
def test_creation_and_enqueue(payload, django_capture_on_commit_callbacks):
    with (
        patch("apps.inquiries.api.notify_atelier.delay") as atelier,
        patch("apps.inquiries.api.send_acknowledgement.delay") as ack,
        django_capture_on_commit_callbacks(execute=True),
    ):
        response = APIClient().post("/api/v1/contact", payload, format="json")
    assert response.status_code == 201 and response.data == {"received": True}
    inquiry = ContactInquiry.objects.get()
    assert inquiry.privacy_version == 3
    atelier.assert_called_once_with(inquiry.pk)
    ack.assert_called_once_with(inquiry.pk)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "field,value",
    [("email", "incorrecto"), ("name", "x" * 121), ("message", "breve"), ("topic", "desconocido")],
)
def test_validation(payload, field, value):
    payload[field] = value
    response = APIClient().post("/api/v1/contact", payload, format="json")
    assert response.status_code == 422 and field in response.data["errors"]


@pytest.mark.django_db
@pytest.mark.parametrize("version", [None, 2])
def test_consent(payload, version):
    payload["accepted_privacy_version"] = version
    response = APIClient().post("/api/v1/contact", payload, format="json")
    assert response.status_code == 422 and response.data["code"] == "consent_required"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "field,value", [("website", "spam"), ("elapsed_ms", 2999), ("elapsed_ms", "100")]
)
def test_silent_spam(payload, field, value):
    payload[field] = value
    with patch("apps.inquiries.api.notify_atelier.delay") as delay:
        assert APIClient().post("/api/v1/contact", payload, format="json").status_code == 201
    assert not ContactInquiry.objects.exists()
    delay.assert_not_called()


@pytest.mark.django_db
def test_throttle(payload):
    client = APIClient()
    payload["website"] = "spam"
    for _ in range(3):
        assert client.post("/api/v1/contact", payload, format="json").status_code == 201
    assert client.post("/api/v1/contact", payload, format="json").status_code == 429


@pytest.mark.django_db
def test_emails(payload, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    config = get_solo()
    config.support_email = "atelier@example.com"
    config.save()
    payload.pop("accepted_privacy_version")
    payload.pop("elapsed_ms")
    payload.pop("website")
    inquiry = ContactInquiry.objects.create(privacy_version=3, **payload)
    notify_atelier(inquiry.pk)
    send_acknowledgement(inquiry.pk)
    assert len(mail.outbox) == 2
    assert mail.outbox[0].reply_to == ["ana@example.com"]
    assert mail.outbox[0].to == ["atelier@example.com"]
    assert "We received your letter, Ana" in mail.outbox[1].body
    assert inquiry.message not in mail.outbox[1].body
    assert "SERTI · Colombia" in mail.outbox[1].body
    assert "atelier@example.com" in mail.outbox[1].body
    assert "<html" in mail.outbox[1].alternatives[0].content


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role,allowed", [("Propietario", True), ("Operaciones", True), ("Contenido", False)]
)
def test_admin_roles(role, allowed):
    sync_roles()
    user = User.objects.create_user(
        username=role, email=f"{role}@example.com", password="test", is_staff=True
    )
    user.groups.add(Group.objects.get(name=role))
    request = RequestFactory().get("/")
    request.user = user
    model_admin = admin.site._registry[ContactInquiry]
    assert model_admin.has_view_permission(request) is allowed
    assert model_admin.has_change_permission(request) is allowed


@pytest.mark.django_db
def test_admin_actions(payload):
    payload.pop("accepted_privacy_version")
    payload.pop("elapsed_ms")
    payload.pop("website")
    inquiry = ContactInquiry.objects.create(privacy_version=3, **payload)
    model_admin = admin.site._registry[ContactInquiry]
    request = RequestFactory().post("/")
    request.user = User.objects.create_user(username="operator", is_staff=True)
    model_admin.mark_answered(request, ContactInquiry.objects.all())
    inquiry.refresh_from_db()
    assert inquiry.status == "answered" and inquiry.answered_at
    model_admin.archive(request, ContactInquiry.objects.all())
    inquiry.refresh_from_db()
    assert inquiry.status == "archived"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "phone,expected",
    [("3001112233", "+573001112233"), ("+573001112233", "+573001112233"),
     ("(300) 111-2233", "+573001112233")],
)
def test_phone_normalization(payload, phone, expected):
    payload["phone"] = phone
    with patch("apps.inquiries.api.notify_atelier.delay"), patch(
        "apps.inquiries.api.send_acknowledgement.delay"
    ):
        response = APIClient().post("/api/v1/contact", payload, format="json")
    assert response.status_code == 201
    inquiry = ContactInquiry.objects.get()
    assert inquiry.phone == expected
    assert "wa.me/573001112233" in str(admin.site._registry[ContactInquiry].reply_links(inquiry))


@pytest.mark.django_db
@pytest.mark.parametrize("phone", ["123", "abc12345678", "1234567890123456"])
def test_invalid_phone(payload, phone):
    payload["phone"] = phone
    response = APIClient().post("/api/v1/contact", payload, format="json")
    assert response.status_code == 422 and "phone" in response.data["errors"]


@pytest.mark.django_db
def test_answered_date_on_individual_save(payload):
    for key in ("accepted_privacy_version", "elapsed_ms", "website"):
        payload.pop(key)
    inquiry = ContactInquiry.objects.create(privacy_version=3, **payload)
    inquiry.status = "answered"
    inquiry.save(update_fields=["status"])
    inquiry.refresh_from_db()
    assert inquiry.answered_at
    answered_at = inquiry.answered_at
    inquiry.save()
    assert inquiry.answered_at == answered_at
    inquiry.status = "new"
    inquiry.save(update_fields=["status"])
    inquiry.refresh_from_db()
    assert inquiry.answered_at is None


@pytest.mark.django_db
def test_admin_status_audit_individual_and_bulk(payload):
    from apps.audit.models import AuditLog

    for key in ("accepted_privacy_version", "elapsed_ms", "website"):
        payload.pop(key)
    inquiry = ContactInquiry.objects.create(privacy_version=3, **payload)
    request = RequestFactory().post("/")
    request.user = User.objects.create_user(username="auditor", is_staff=True)
    model_admin = admin.site._registry[ContactInquiry]
    inquiry.status = "answered"
    model_admin.save_model(request, inquiry, None, True)
    model_admin.archive(request, ContactInquiry.objects.filter(pk=inquiry.pk))
    model_admin.archive(request, ContactInquiry.objects.filter(pk=inquiry.pk))
    inquiry.refresh_from_db()
    inquiry.status = "new"
    model_admin.save_model(request, inquiry, None, True)
    events = AuditLog.objects.filter(object_id=str(inquiry.pk), action__startswith="inquiries.")
    assert set(events.values_list("action", flat=True)) == {
        "inquiries.answered", "inquiries.archived", "inquiries.status_changed"
    }
    assert events.count() == 3
    assert all(set(event.diff) == {"status"} and inquiry.message not in str(event.diff)
               for event in events)
