from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.roles import OPERACIONES, PROPIETARIO
from apps.audit.models import AuditLog
from apps.core.formatting import format_bogota_datetime, format_cop
from apps.core.selectors import get_solo
from apps.core.tests.test_dashboard_client import staff
from apps.notifications.presentation import communication_rows
from apps.notifications.rendering import render_email
from apps.notifications.services import can_resend, deliver, enqueue, resend, send_copy
from apps.orders.incidents import open_incident
from apps.orders.models import OrderIncident
from apps.orders.services import cancel_order
from apps.payments.services import apply_transaction
from apps.payments.tests.test_payments import tx_for

pytestmark = pytest.mark.django_db
CUSTOMER_EVENTS = [
    "order_received",
    "payment_issue",
    "order_paid",
    "order_preparing",
    "order_shipped",
    "order_delivered",
    "order_cancelled",
    "manual_payment_instructions",
    "reservation_expired",
]


def request_for(user):
    request = RequestFactory().post("/")
    request.user = user
    return request


def row_for(order, event="order_paid"):
    enqueue(order, event)
    return order.deliveries.get(event=event, audience="customer")


@pytest.mark.parametrize("locale", ["es", "en"])
@pytest.mark.parametrize("event", CUSTOMER_EVENTS)
@override_settings(PUBLIC_SITE_URL="https://serti.example")
def test_complete_templates(order, locale, event):
    config = get_solo()
    config.support_email = "hola@serti.example"
    config.whatsapp_number = "573009998877"
    config.save()
    order.locale = locale
    order.payment_channel = "manual" if event == "manual_payment_instructions" else "wompi"
    order.paid_at = timezone.now() - timedelta(days=1)
    order.wants_certificate = True
    order.discount_cents, order.shipping_cents, order.certificate_cents = 1000, 2000, 3000
    order.total_cents = order.subtotal_cents + 4000
    order.carrier, order.tracking_number, order.tracking_url = (
        "Carrier",
        "GUIA",
        "https://carrier.example/1",
    )
    order.save()
    content = render_email(row_for(order, event), order)
    item = order.items.get()
    for body in [content.html, content.text]:
        for value in [
            order.number,
            order.customer_name,
            item.name_en if locale == "en" else item.name_es,
            item.sku,
            format_cop(order.total_cents, locale),
            order.shipping_address_line,
            order.public_token,
            config.support_email,
            "https://wa.me/573009998877",
        ]:
            assert value in body
        for amount in [
            order.subtotal_cents,
            order.discount_cents,
            order.shipping_cents,
            order.certificate_cents,
        ]:
            assert format_cop(amount, locale) in body
        assert order.customer_phone not in body
        assert "None" not in body and "{{" not in body
        if event == "order_shipped":
            assert all(
                value in body
                for value in [order.carrier, order.tracking_number, order.tracking_url]
            )
    assert content.subject.startswith(
        f"SERTI · {'Pedido' if locale == 'es' else 'Order'} {order.number} · "
    )
    assert (
        'width="600"' in content.html
        and "https://serti.example/brand/monogram-email.png" in content.html
    )


@pytest.mark.parametrize("locale", ["es", "en"])
@override_settings(PUBLIC_SITE_URL="")
def test_no_broken_logo_or_contact(order, locale):
    order.locale = locale
    order.save()
    config = get_solo()
    config.support_email, config.whatsapp_number = "", ""
    config.save()
    content = render_email(row_for(order), order)
    assert "<img" not in content.html and "SERTI" in content.html
    assert "mailto:" not in content.html and "wa.me" not in content.html


@pytest.mark.parametrize("locale", ["es", "en"])
def test_paid_date(order, locale):
    order.locale, order.paid_at = locale, timezone.now() - timedelta(days=3)
    order.save()
    content = render_email(row_for(order), order)
    for body in [content.html, content.text]:
        assert format_bogota_datetime(order.paid_at, locale) in body
        assert format_bogota_datetime(order.created_at, locale) not in body
        assert "preparando" not in body and "begun preparing" not in body


def test_received_only_pending_once(order):
    assert not order.deliveries.exists()
    pending = replace(tx_for(order), status="PENDING", payment_method_type="PSE")
    assert apply_transaction(pending, source="webhook") == "applied"
    assert apply_transaction(pending, source="reconcile") == "duplicate"
    assert order.deliveries.filter(event="order_received").count() == 1
    assert not order.deliveries.filter(event="order_received", audience="serti").exists()
    apply_transaction(tx_for(order), source="webhook")
    apply_transaction(pending, source="reconcile")
    assert order.deliveries.filter(event="order_received").count() == 1


@pytest.mark.parametrize("manual", [True, False])
def test_no_received_for_manual_or_direct_approval(order, manual):
    if manual:
        order.payment_channel = "manual"
        order.save()
    apply_transaction(
        replace(tx_for(order), status="PENDING" if manual else "APPROVED"), source="webhook"
    )
    assert not order.deliveries.filter(event="order_received").exists()


@pytest.mark.parametrize("kind", OrderIncident.Kind.values)
def test_payment_issue_only_two_kinds_per_incident(order, kind):
    first = open_incident(order, kind)
    assert open_incident(order, kind).pk == first.pk
    expected = int(kind in {"no_piece", "cancelled_payment"})
    assert order.deliveries.filter(event="payment_issue").count() == expected
    first.status = "resolved"
    first.save()
    assert open_incident(order, kind).pk != first.pk
    assert order.deliveries.filter(event="payment_issue").count() == 2 * expected
    if expected:
        body = render_email(order.deliveries.filter(event="payment_issue").first(), order).text
        assert "menos de 1 día hábil" in body and "disponible" not in body


@pytest.mark.parametrize("include", [False, True])
@pytest.mark.parametrize("paid", [False, True])
def test_cancel_reason_refund(order, include, paid):
    _, owner = staff(PROPIETARIO)
    if paid:
        apply_transaction(tx_for(order), source="webhook")
    cancel_order(
        order,
        actor=owner,
        reason="Motivo privado del cliente",
        notify=True,
        expected_status="unfulfilled",
        include_reason=include,
    )
    order.refresh_from_db()
    content = render_email(
        order.deliveries.get(event="order_cancelled", audience="customer"), order
    )
    for body in [content.html, content.text]:
        assert ("Motivo privado del cliente" in body) is include
        assert ("Te contactaremos para la devolución de tu dinero" in body) is paid
    assert AuditLog.objects.filter(action="orders.cancelled").exists()


def test_log_skipped_reconfiguration_audit(order):
    from .test_notifications import CLOUD

    _, owner = staff(PROPIETARIO)
    enqueue(order, "order_paid")
    row = order.deliveries.get(channel="whatsapp")
    with patch("apps.notifications.adapters.urlopen") as network:
        deliver(row.pk)
    network.assert_not_called()
    row.refresh_from_db()
    assert row.status == "skipped" and row.last_error == "whatsapp_simulation" and not row.sent_at
    assert not can_resend(row)
    with override_settings(**CLOUD), patch("apps.notifications.services.dispatch"):
        assert can_resend(row) and resend(row.pk, request=request_for(owner))
    assert AuditLog.objects.filter(action="notifications.resent", object_id=str(row.pk)).exists()


@override_settings(SERTI_ORDERS_EMAIL="")
def test_email_reconfigured(order):
    _, owner = staff(PROPIETARIO)
    enqueue(order, "order_paid")
    row = order.deliveries.get(channel="email", audience="serti")
    deliver(row.pk)
    row.refresh_from_db()
    assert not can_resend(row)
    with (
        override_settings(SERTI_ORDERS_EMAIL="orders@serti.example"),
        patch("apps.notifications.services.dispatch"),
    ):
        assert resend(row.pk, request=request_for(owner))
        deliver(row.pk)
    row.refresh_from_db()
    assert row.status == "sent"


def test_copy_limit_snapshot_audit(order):
    _, owner = staff(PROPIETARIO)
    row = row_for(order)
    deliver(row.pk)
    row.refresh_from_db()
    original = render_email(row, order).html
    order.shipping_address_line = "Otra dirección"
    order.save()
    assert render_email(row, order).html == original
    with patch("apps.notifications.services.dispatch"):
        first = send_copy(row.pk, request=request_for(owner))
        deliver(first.pk)
        second = send_copy(first.pk, request=request_for(owner))
        third = send_copy(row.pk, request=request_for(owner))
        with pytest.raises(ValidationError, match="máximo de 3"):
            send_copy(row.pk, request=request_for(owner))
    assert len({first.idempotency_key, second.idempotency_key, third.idempotency_key}) == 3
    assert render_email(first, order).html == original
    assert AuditLog.objects.filter(action="notifications.copied", actor=owner).count() == 3


@pytest.mark.parametrize("action", ["copy", "resend"])
def test_http_permissions_confirmation(order, action):
    browser, operator = staff(OPERACIONES)
    operator.groups.clear()
    operator.user_permissions.add(Permission.objects.get(codename="view_order"))
    row = row_for(order)
    row.status = "sent" if action == "copy" else "failed"
    row.save()
    endpoint = reverse("admin:orders-card-communication", args=[order.pk])
    data = {"delivery_id": row.pk, "action": action, "confirm": "yes"}
    assert browser.post(endpoint, data).status_code == 403
    operator.user_permissions.add(Permission.objects.get(codename="resend_notificationdelivery"))
    with patch("apps.notifications.services.dispatch"):
        assert browser.post(endpoint, {**data, "confirm": ""}).status_code == 422
        assert browser.post(endpoint, data).status_code == 200
    assert browser.get(endpoint).status_code == 405


def test_card_masked_states_preview_permissions(order):
    browser, owner = staff(PROPIETARIO)
    row = row_for(order)
    deliver(row.pk)
    html = browser.get(reverse("admin:orders-card", args=[order.pk])).content.decode()
    section = html.split("<h3>Comunicaciones</h3>", 1)[1].split("<h3>Historial", 1)[0]
    assert "Pago aprobado" in section and "Aceptado por el proveedor" in section
    assert "t***@example.com" in section and order.customer_email not in section
    assert "Enviar copia al cliente" in section and "Ver correo" in section
    endpoint = reverse("admin:orders-card-email", args=[order.pk, row.pk])
    preview = browser.get(endpoint)
    row.refresh_from_db()
    assert (
        preview.status_code == 200 and preview.content.decode() == row.payload["rendered"]["html"]
    )
    assert "sandbox" in preview["Content-Security-Policy"]
    assert browser.post(endpoint).status_code == 405
    assert (
        browser.get(reverse("admin:orders-card-email", args=[order.pk + 1, row.pk])).status_code
        == 404
    )
    owner.groups.clear()
    assert browser.get(endpoint).status_code == 403


def test_errors_safe(order):
    row = row_for(order)
    row.status, row.last_error = "failed", "legacy secret@email.test +573000000000"
    row.save()
    error = communication_rows(order, can_manage=True)[0]["error"]
    assert "secret" not in error and "573" not in error


@pytest.mark.parametrize("locale", ["es", "en"])
@pytest.mark.parametrize(
    "event", ["order_paid", "order_cancelled", "needs_attention", "incident_resolved"]
)
def test_internal_locale_incident(order, locale, event):
    order.locale = locale
    order.save()
    enqueue(order, event, audience="serti", metadata={"incident_kind": "cancelled_payment"})
    row = order.deliveries.get(event=event, channel="email")
    content = render_email(row, order)
    for body in [content.html, content.text]:
        assert (
            "Pago recibido en pedido cancelado"
            if locale == "es"
            else "Payment received for a cancelled order"
        ) in body
        assert order.customer_phone not in body
        assert reverse("admin:orders_order_change", args=[order.pk]) in body
    assert row.locale == locale


def test_migration_normalizes_only_simulated_whatsapp(order):
    from importlib import import_module
    from types import SimpleNamespace

    from django.apps import apps
    from django.db import connection

    enqueue(order, "order_paid")
    simulated = order.deliveries.get(channel="whatsapp")
    simulated.status, simulated.provider_message_id, simulated.sent_at = (
        "sent",
        "log-123",
        timezone.now(),
    )
    simulated.save()
    real_email = order.deliveries.get(channel="email", audience="customer")
    real_email.status, real_email.provider_message_id = "sent", "log-123"
    real_email.save()
    migrate = import_module(
        "apps.notifications.migrations.0006_notificationdelivery_payload_and_more"
    )
    migrate.normalize_simulated_whatsapp(apps, SimpleNamespace(connection=connection))
    simulated.refresh_from_db()
    real_email.refresh_from_db()
    assert simulated.status == "skipped" and simulated.last_error == "whatsapp_simulation"
    assert simulated.sent_at is None and real_email.status == "sent"


@pytest.mark.parametrize(
    "status,channel,audience",
    [
        ("failed", "email", "customer"),
        ("queued", "email", "customer"),
        ("sent", "whatsapp", "serti"),
        ("sent", "email", "serti"),
    ],
)
def test_copy_rejects_other_deliveries(order, status, channel, audience):
    _, owner = staff(PROPIETARIO)
    enqueue(order, "order_paid")
    row = order.deliveries.get(channel=channel, audience=audience)
    row.status = status
    row.save()
    with pytest.raises(ValidationError):
        send_copy(row.pk, request=request_for(owner))
    assert not AuditLog.objects.filter(action="notifications.copied").exists()


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_concurrent_copies_cannot_exceed_limit(order):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections, connection

    from apps.accounts.models import User

    owner = User.objects.create_superuser(username="copy-race", password="test")
    row = row_for(order)
    deliver(row.pk)
    barrier = Barrier(2)
    with patch("apps.notifications.services.dispatch"):
        send_copy(row.pk, request=request_for(owner))
        send_copy(row.pk, request=request_for(owner))

        def attempt(_):
            close_old_connections()
            try:
                user = User.objects.get(pk=owner.pk)
                barrier.wait(timeout=10)
                send_copy(row.pk, request=request_for(user))
                return "created"
            except ValidationError:
                return "limited"
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, range(2)))
    assert sorted(results) == ["created", "limited"]
    assert order.deliveries.filter(idempotency_key__contains=":copy:").count() == 3
    assert AuditLog.objects.filter(action="notifications.copied").count() == 3
