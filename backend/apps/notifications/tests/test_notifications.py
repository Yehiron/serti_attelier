from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.contrib.admin.sites import site
from django.contrib.auth.models import Group
from django.core import mail
from django.core.exceptions import PermissionDenied
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.test import RequestFactory, override_settings
from django.urls import resolve, reverse
from django.utils import timezone
from django.utils.translation import override
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.catalog.models import Piece
from apps.core.formatting import format_bogota_datetime, format_cop
from apps.core.routes import href
from apps.core.selectors import get_solo
from apps.inventory.services import release_reservation
from apps.notifications.adapters import ChannelFailure, send_whatsapp
from apps.notifications.admin import NotificationDeliveryAdmin
from apps.notifications.models import NotificationDelivery
from apps.notifications.rendering import order_context, render_email, whatsapp_parameters
from apps.notifications.services import BACKOFF_SECONDS, deliver, enqueue, resend
from apps.notifications.tasks import retry_failed, send_delivery
from apps.orders import events
from apps.orders.models import Order
from apps.orders.services import expire_stale_orders
from apps.orders.tests.test_checkout import add, submit
from apps.payments.services import apply_transaction, confirm_manual_payment
from apps.payments.tests.test_payments import URL, event, proof, tx_for
from apps.promotions.services import email_digest

pytestmark = pytest.mark.django_db


def queued(order: Order, event_name: str = "order_paid") -> NotificationDelivery:
    enqueue(order, event_name)
    return NotificationDelivery.objects.get(order=order, event=event_name, audience="customer")


@pytest.mark.parametrize(
    "event_name,targets",
    [
        ("order_paid", {("email", "customer"), ("email", "serti"), ("whatsapp", "serti")}),
        ("manual_payment_instructions", {("email", "customer"), ("email", "serti")}),
        ("reservation_expired", {("email", "customer")}),
        ("needs_attention", {("email", "serti"), ("whatsapp", "serti")}),
    ],
)
def test_event_targets_and_idempotency(
    order: Order,
    event_name: str,
    targets: set[tuple[str, str]],
    django_capture_on_commit_callbacks: Any,
) -> None:
    with patch("apps.notifications.tasks.send_delivery.delay") as delay:
        with django_capture_on_commit_callbacks(execute=True):
            assert enqueue(order, event_name) == len(targets)
            assert enqueue(order, event_name) == 0
            delay.assert_not_called()
        assert delay.call_count == len(targets)
    rows = NotificationDelivery.objects.filter(event=event_name)
    assert set(rows.values_list("channel", "audience")) == targets
    for row in rows:
        assert len(row.recipient_hash) == 64
        assert order.customer_email not in str(row.__dict__)
        assert order.customer_phone not in str(row.__dict__)


def test_rollback_never_dispatches(order: Order, django_capture_on_commit_callbacks: Any) -> None:
    with patch("apps.notifications.tasks.send_delivery.delay") as delay:
        with (
            django_capture_on_commit_callbacks(execute=True),
            pytest.raises(ValueError),
            transaction.atomic(),
        ):
            enqueue(order, "order_paid")
            raise ValueError
        delay.assert_not_called()
    assert not NotificationDelivery.objects.exists()


@pytest.mark.parametrize("locale", ["es", "en"])
@pytest.mark.parametrize("certificate", [True, False])
def test_confirmation_email(order: Order, locale: str, certificate: bool) -> None:
    order.locale = locale
    order.wants_certificate = certificate
    order.payment_status = "approved"
    order.save()
    config = get_solo()
    config.support_email = "support@example.com"
    config.whatsapp_number = "573001112233"
    config.save()
    delivery = queued(order)
    send_delivery(delivery.pk)
    delivery.refresh_from_db()
    assert delivery.status == "sent" and delivery.sent_at
    message = cast(EmailMultiAlternatives, mail.outbox[-1])
    assert order.number and order.number in message.subject
    assert (
        "Confirmación de compra" if locale == "es" else "Purchase confirmation"
    ) in message.subject
    assert delivery.provider_message_id == message.extra_headers["Message-ID"]
    assert message.from_email == settings.DEFAULT_FROM_EMAIL
    assert message.reply_to == [config.support_email]
    assert message.alternatives and message.alternatives[0][1] == "text/html"
    html = cast(str, message.alternatives[0][0])
    for body in (message.body, html):
        assert format_cop(order.total_cents, locale) in body
        assert order.shipping_address_line in body
        assert settings.PUBLIC_SITE_URL + href("order", locale, order) in body
        assert format_bogota_datetime(order.created_at, locale) in body
        # The certificate line only appears when the customer asked for one.
        certificate_label = (
            "Certificado de autenticidad" if locale == "es" else "Certificate of authenticity"
        )
        assert (certificate_label in body) is certificate
        assert ("gratis en Colombia" if locale == "es" else "free in Colombia") in body.replace(
            "Free in", "free in"
        ).replace("Gratis en", "gratis en")
        assert "factura" not in body.lower() and "invoice" not in body.lower()
    assert 'lang="' + locale + '"' in html and "/brand/monogram-email.png" in html
    assert "#591e24" in html and "#e9e3d0" in html
    before = len(mail.outbox)
    send_delivery(delivery.pk)
    assert len(mail.outbox) == before
    assert delivery.recipient_hash == email_digest(order.customer_email)


@pytest.mark.parametrize("locale", ["es", "en"])
def test_every_template_has_no_forbidden_terms(order: Order, locale: str) -> None:
    order.locale = locale
    order.payment_channel = "manual"
    context = order_context(order, locale)
    context.update(title="SERTI", event="needs_attention")
    paths = list((settings.BASE_DIR / "templates" / "emails" / locale).glob("*"))
    assert len(paths) == 10
    for path in paths:
        body = render_to_string(f"emails/{locale}/{path.name}", context)
        assert "factura" not in body.lower() and "invoice" not in body.lower()
        assert body.strip()
    # The common wrapper must obey the same content restriction.
    assert "invoice" not in (settings.BASE_DIR / "templates/emails/base.html").read_text().lower()


@override_settings(SERTI_ORDERS_EMAIL="orders@example.com")
@pytest.mark.parametrize(
    "event_name", ["order_paid", "manual_payment_instructions", "needs_attention"]
)
def test_internal_content_and_admin_link(order: Order, event_name: str) -> None:
    enqueue(order, event_name)
    row = NotificationDelivery.objects.get(event=event_name, channel="email", audience="serti")
    content = render_email(row, order)
    path = reverse("admin:orders_order_change", args=[order.pk])
    assert resolve(path).url_name == "orders_order_change"
    for value in [
        order.customer_name,
        order.customer_email,
        order.customer_phone,
        order.shipping_address_line,
        order.items.get().sku,
        settings.PUBLIC_SITE_URL + path,
    ]:
        assert value in content.text
    if event_name == "needs_attention":
        assert "URGENTE" in content.subject
        assert "Requiere reembolso o contacto con el cliente" in content.text
    deliver(row.pk)
    assert mail.outbox[-1].to == ["orders@example.com"]


def test_manual_creation_and_expiry(
    client: APIClient,
    piece: Piece,
    payload: dict[str, Any],
    django_capture_on_commit_callbacks: Any,
) -> None:
    payload["payment_channel"] = "manual"
    add(client, piece)
    with django_capture_on_commit_callbacks(execute=True):
        response = submit(client, payload)
    order = Order.objects.get(public_token=response.data["public_token"])
    assert order.deliveries.filter(event="manual_payment_instructions").count() == 2
    message = cast(EmailMultiAlternatives, mail.outbox[-1])
    assert "Instrucciones de pago" in message.subject
    assert format_cop(order.total_cents, "es") in message.body
    assert order.reservation_expires_at
    assert format_bogota_datetime(order.reservation_expires_at, "es") in message.body
    assert "Efecty" in message.body
    config = get_solo()
    config.whatsapp_number = "573001112233"
    config.save()
    release_reservation(order.reservations.get().pk, reason="reservation_expired")
    with django_capture_on_commit_callbacks(execute=True):
        assert expire_stale_orders() == 1
        assert expire_stale_orders() == 0
    assert order.deliveries.filter(event="reservation_expired").count() == 1
    assert "Tu reserva venció" in mail.outbox[-1].subject
    assert href("catalog", "es") in mail.outbox[-1].body
    assert "https://wa.me/573001112233" in mail.outbox[-1].body


@override_settings(WOMPI_EVENTS_SECRET="secret")
def test_double_webhook_one_set(
    order: Order, client: APIClient, django_capture_on_commit_callbacks: Any
) -> None:
    body = event(tx_for(order))
    with django_capture_on_commit_callbacks(execute=True):
        assert client.post(URL, body, format="json").status_code == 200
        assert client.post(URL, body, format="json").status_code == 200
    assert order.deliveries.filter(event="order_paid").count() == 3
    assert len(mail.outbox) == 1


@pytest.mark.parametrize("scenario", ["late", "mismatch", "voided", "incompatible"])
def test_attention_hooks(
    order: Order, scenario: str, django_capture_on_commit_callbacks: Any
) -> None:
    tx = tx_for(order)
    with django_capture_on_commit_callbacks(execute=True):
        if scenario == "late":
            release_reservation(order.reservations.get().pk, reason="reservation_expired")
            expire_stale_orders()
            Piece.objects.filter(pk=order.items.get().piece_id).update(sale_state="sold")
        elif scenario == "mismatch":
            tx = replace(tx, currency="USD")
        elif scenario == "voided":
            apply_transaction(tx, source="webhook")
            tx = replace(tx, status="VOIDED")
        elif scenario == "incompatible":
            order.payment_attempts.update(status="VOIDED")
        apply_transaction(tx, source="webhook")
    order.refresh_from_db()
    assert order.needs_attention
    assert order.deliveries.filter(event="needs_attention").count() == 2


def test_smtp_failure_never_reverts_payment(
    order: Order, django_capture_on_commit_callbacks: Any
) -> None:
    with (
        patch(
            "apps.notifications.adapters.EmailMultiAlternatives.send",
            side_effect=OSError("secret@example.com token 573001234567"),
        ),
        django_capture_on_commit_callbacks(execute=True),
    ):
        apply_transaction(tx_for(order), source="webhook")
    order.refresh_from_db()
    assert order.payment_status == "approved" and order.paid_at
    assert order.payment_attempts.get().status == "APPROVED"
    row = order.deliveries.get(audience="customer")
    # Only the exception type is kept: no address, token or phone from the message body.
    assert row.status == "failed"
    assert row.last_error == "delivery_failed:email_send_failed:OSError"
    assert "secret@example.com" not in row.last_error and "573001234567" not in row.last_error


def test_hook_and_broker_failure_sanitized(
    order: Order, caplog: Any, django_capture_on_commit_callbacks: Any
) -> None:
    with patch("apps.notifications.services.enqueue", side_effect=OSError("private@email.test")):
        events.order_paid(order.pk)
        events.manual_order_created(order.pk)
        events.order_expired(order.pk)
        events.order_needs_attention(order.pk)
    with (
        patch("apps.notifications.tasks.send_delivery.delay", side_effect=OSError("secret")),
        django_capture_on_commit_callbacks(execute=True),
    ):
        enqueue(order, "order_paid")
    assert "private@email.test" not in caplog.text and "secret" not in caplog.text
    assert order.deliveries.filter(status="queued").count() == 3
    assert retry_failed() == 3
    assert order.deliveries.get(audience="customer").status == "sent"


def test_retries_and_gave_up(
    order: Order, django_capture_on_commit_callbacks: Any, caplog: Any
) -> None:
    row = queued(order)
    for attempt in range(1, 6):
        with (
            patch("apps.notifications.adapters.send_email", side_effect=OSError("PII")),
            patch("apps.notifications.tasks.send_delivery.apply_async") as schedule,
            django_capture_on_commit_callbacks(execute=True),
        ):
            deliver(row.pk)
        row.refresh_from_db()
        assert row.attempts == attempt and row.last_error == "delivery_failed:OSError"
        if attempt < 5:
            assert row.status == "failed" and row.next_attempt_at
            schedule.assert_called_once_with(args=[row.pk], countdown=BACKOFF_SECONDS[attempt - 1])
            seconds = (row.next_attempt_at - timezone.now()).total_seconds()
            assert BACKOFF_SECONDS[attempt - 1] - 3 <= seconds <= BACKOFF_SECONDS[attempt - 1]
            deliver(row.pk)
            row.refresh_from_db()
            assert row.attempts == attempt
            NotificationDelivery.objects.filter(pk=row.pk).update(next_attempt_at=timezone.now())
        else:
            assert row.status == "gave_up" and row.next_attempt_at is None
            schedule.assert_not_called()
    deliver(row.pk)
    assert "gave up" in caplog.text and "PII" not in caplog.text


def test_beat_only_due_rows(order: Order) -> None:
    row = queued(order)
    NotificationDelivery.objects.filter(pk=row.pk).update(
        status="failed", next_attempt_at=timezone.now() + timedelta(minutes=2)
    )
    with patch("apps.notifications.tasks.send_delivery.delay") as delay:
        retry_failed()
        assert row.pk not in [call.args[0] for call in delay.call_args_list]
        NotificationDelivery.objects.filter(pk=row.pk).update(next_attempt_at=timezone.now())
        retry_failed()
        assert row.pk in [call.args[0] for call in delay.call_args_list]


@override_settings(WHATSAPP_PROVIDER="cloud", SERTI_ORDERS_EMAIL="")
def test_skipped_unconfigured(order: Order) -> None:
    order.customer_email = ""
    order.save()
    enqueue(order, "order_paid")
    with patch("apps.notifications.adapters.urlopen") as network:
        for row in order.deliveries.all():
            deliver(row.pk)
        network.assert_not_called()
    assert order.deliveries.filter(status="skipped", attempts=0).count() == 3
    for row in order.deliveries.all():
        deliver(row.pk)
    assert not mail.outbox


@override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="")
def test_smtp_host_unconfigured(order: Order) -> None:
    row = queued(order)
    with patch("apps.notifications.adapters.send_email") as send:
        deliver(row.pk)
        send.assert_not_called()
    row.refresh_from_db()
    assert row.status == "skipped" and row.last_error == "email_smtp_unconfigured"


@override_settings(WHATSAPP_PROVIDER="log", WHATSAPP_ORDERS_RECIPIENT="")
def test_log_never_network(order: Order, caplog: Any) -> None:
    with patch("apps.notifications.adapters.urlopen") as network:
        assert send_whatsapp("order_paid", whatsapp_parameters(order, "order_paid"), 1) == "log-1"
        network.assert_not_called()
    assert order.customer_name not in caplog.text and order.customer_phone not in caplog.text


CLOUD = {
    "WHATSAPP_PROVIDER": "cloud",
    "WHATSAPP_API_VERSION": "v26.0",
    "WHATSAPP_PHONE_NUMBER_ID": "123456",
    "WHATSAPP_ACCESS_TOKEN": "very-secret-token",
    "WHATSAPP_ORDERS_RECIPIENT": "573001234567",
    "WHATSAPP_TEMPLATE_NEW_ORDER": "nuevo_pedido",
    "WHATSAPP_TEMPLATE_NEEDS_ATTENTION": "pedido_requiere_atencion",
    "WHATSAPP_TEMPLATE_LANG": "es",
}


@override_settings(**CLOUD)
@pytest.mark.parametrize("event_name", ["order_paid", "needs_attention"])
def test_cloud_contract(order: Order, event_name: str) -> None:
    response = MagicMock()
    response.__enter__.return_value = response
    response.status = 200
    response.read.return_value = b'{"messages":[{"id":"wamid.ABC123"}]}'
    params = whatsapp_parameters(order, event_name)
    assert params[:7] == [
        order.number,
        "Cliente",
        "Anillo",
        format_cop(order.total_cents, "es"),
        "Medellín, Antioquia",
        "No",
        settings.PUBLIC_SITE_URL + reverse("admin:orders_order_change", args=[order.pk]),
    ]
    with patch("apps.notifications.adapters.urlopen", return_value=response) as send:
        assert send_whatsapp(event_name, params, 3) == "wamid.ABC123"
    request = send.call_args.args[0]
    assert request.full_url == "https://graph.facebook.com/v26.0/123456/messages"
    assert request.method == "POST"
    assert request.get_header("Authorization") == "Bearer very-secret-token"
    assert request.get_header("Content-type") == "application/json"
    assert send.call_args.kwargs == {"timeout": 10}
    assert json.loads(request.data) == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "573001234567",
        "type": "template",
        "template": {
            "name": "pedido_requiere_atencion"
            if event_name == "needs_attention"
            else "nuevo_pedido",
            "language": {"code": "es"},
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}
            ],
        },
    }


@override_settings(**CLOUD)
@pytest.mark.parametrize(
    "error",
    [TimeoutError("573001234567 very-secret-token"), OSError("573001234567 very-secret-token")],
)
def test_cloud_failures_sanitized(order: Order, error: Exception, caplog: Any) -> None:
    enqueue(order, "needs_attention")
    row = order.deliveries.get(channel="whatsapp")
    with patch("apps.notifications.adapters.urlopen", side_effect=error):
        deliver(row.pk)
    row.refresh_from_db()
    assert row.status == "failed" and row.attempts == 1
    assert "573001234567" not in row.last_error + caplog.text
    assert "very-secret-token" not in row.last_error + caplog.text


@override_settings(**CLOUD)
@pytest.mark.parametrize("body", [b"{}", b"not json", b'{"messages":[{"id":""}]}'])
def test_cloud_bad_response(body: bytes) -> None:
    response = MagicMock()
    response.__enter__.return_value = response
    response.status = 200
    response.read.return_value = body
    with (
        patch("apps.notifications.adapters.urlopen", return_value=response),
        pytest.raises(ChannelFailure, match="whatsapp_send_failed"),
    ):
        send_whatsapp("order_paid", ["value"], 1)


@pytest.mark.parametrize(
    "role,allowed", [("Propietario", True), ("Operaciones", True), ("Contenido", False)]
)
def test_admin_resend_permission_and_audit(
    order: Order, role: str, allowed: bool, django_capture_on_commit_callbacks: Any
) -> None:
    row = queued(order)
    NotificationDelivery.objects.filter(pk=row.pk).update(status="gave_up", attempts=5)
    user = User.objects.create_user(username=role, email=f"{role}@example.com", is_staff=True)
    user.groups.add(Group.objects.get(name=role))
    request = RequestFactory().post("/")
    request.user = user
    model_admin = cast(NotificationDeliveryAdmin, site._registry[NotificationDelivery])
    assert model_admin.has_resend_permission(request) is allowed
    assert not model_admin.has_change_permission(request)
    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_delete_permission(request)
    with patch("apps.notifications.tasks.send_delivery.delay") as delay:
        with django_capture_on_commit_callbacks(execute=True):
            if allowed:
                model_admin.resend_failed(request, NotificationDelivery.objects.filter(pk=row.pk))
            else:
                with pytest.raises(PermissionDenied):
                    resend(row.pk, request=request)
        if allowed:
            delay.assert_called_once_with(row.pk)
            row.refresh_from_db()
            assert row.status == "queued" and row.attempts == 0
            assert AuditLog.objects.filter(
                action="notifications.resent", actor=user, object_id=str(row.pk)
            ).exists()
        else:
            delay.assert_not_called()


def test_manual_confirmation_emits_paid(
    order: Order, tmp_path: Path, django_capture_on_commit_callbacks: Any
) -> None:
    order.payment_channel = "manual"
    order.payment_status = "awaiting_manual_payment"
    order.save()
    user = User.objects.create_user(username="operator", email="op@example.com", is_staff=True)
    user.groups.add(Group.objects.get(name="Operaciones"))
    request = RequestFactory().post("/")
    request.user = user
    with (
        override_settings(PRIVATE_MEDIA_ROOT=tmp_path),
        django_capture_on_commit_callbacks(execute=True),
    ):
        confirm_manual_payment(order, actor=user, reference="ref", proof=proof(), request=request)
    assert order.deliveries.filter(event="order_paid").count() == 3


def test_retry_success_and_recipient_change(order: Order) -> None:
    row = queued(order)
    with patch("apps.notifications.adapters.send_email", side_effect=OSError("private")):
        deliver(row.pk)
    NotificationDelivery.objects.filter(pk=row.pk).update(next_attempt_at=timezone.now())
    deliver(row.pk)
    row.refresh_from_db()
    assert row.status == "sent" and row.attempts == 2 and row.last_error == ""
    assert len(mail.outbox) == 1
    deliver(row.pk)
    assert len(mail.outbox) == 1
    enqueue(order, "reservation_expired")
    other = order.deliveries.get(event="reservation_expired")
    order.customer_email = "changed@example.com"
    order.save(update_fields=["customer_email"])
    deliver(other.pk)
    other.refresh_from_db()
    assert other.status == "skipped" and other.last_error == "recipient_changed"
    assert len(mail.outbox) == 1


def test_html_escapes_customer_and_manual_content(order: Order) -> None:
    order.customer_name = '<script>alert("x")</script>'
    order.payment_channel = "manual"
    order.save()
    config = get_solo()
    with override("es"):
        config.manual_payment_instructions = "<b>Payment</b>\n{number} {total}"
        config.save()
    row = queued(order, "manual_payment_instructions")
    content = render_email(row, order)
    assert "&lt;b&gt;Payment&lt;/b&gt;<br>" in content.html
    enqueue(order, "needs_attention")
    internal = order.deliveries.get(event="needs_attention", channel="email")
    assert "<script>" not in render_email(internal, order).html
