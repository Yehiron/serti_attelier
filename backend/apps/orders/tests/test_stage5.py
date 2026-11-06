from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.roles import CONTENIDO, OPERACIONES, PROPIETARIO
from apps.audit.models import AuditLog
from apps.core.tests.test_dashboard_client import staff
from apps.inventory.models import PieceReservation, PieceStatusChange
from apps.inventory.services import decide_cancelled_piece
from apps.notifications.models import (
    AdminNotification,
    AdminNotificationReceipt,
    NotificationDelivery,
)
from apps.notifications.panel import publish, unread_data
from apps.notifications.views import unread
from apps.orders.events import manual_order_created, order_paid
from apps.orders.incidents import open_incident
from apps.orders.metrics import order_center_metrics
from apps.orders.models import OrderItem
from apps.orders.tests.test_card import order as order_fixture
from apps.payments.models import PaymentAttempt, PaymentEvent

order = order_fixture

pytestmark = pytest.mark.django_db


def attempt(order, **kwargs):
    return PaymentAttempt.objects.create(
        order=order,
        sequence=1,
        reference=f"{order.number}-01",
        amount_cents=order.total_cents,
        **kwargs,
    )


def test_metrics_bogota_paid_at_cancelled_and_budget(order, django_assert_num_queries):
    now = datetime(2026, 11, 6, 6, tzinfo=UTC)  # 01:00 Colombia
    order.payment_status = "approved"
    order.paid_at = datetime(2026, 11, 6, 5, tzinfo=UTC)
    order.fulfillment_status = "cancelled"
    order.save()
    with django_assert_num_queries(3):
        cards = order_center_metrics("today", now)
    assert cards[0]["count"] == cards[0]["cancelled_count"] == 1
    assert cards[0]["amount"] == cards[0]["cancelled_amount"]
    assert cards[1]["count"] == 0
    order.paid_at -= timedelta(seconds=1)
    order.save()
    assert order_center_metrics("today", now)[0]["count"] == 0
    assert order_center_metrics("seven_days", now)[0]["count"] == 1
    order.payment_status = "pending"
    order.save()
    assert order_center_metrics("seven_days", now)[0]["count"] == 0


@pytest.mark.parametrize(
    "role,visible", [(PROPIETARIO, True), (OPERACIONES, True), (CONTENIDO, False)]
)
def test_metrics_visibility_and_links(order, role, visible):
    browser, _ = staff(role)
    order.payment_status = "approved"
    order.paid_at = timezone.now()
    order.save()
    response = browser.get(reverse("admin:orders_order_changelist"))
    assert response.status_code == (200 if visible else 403)
    if visible:
        for card in response.context["center_metrics"]:
            filtered = browser.get(card["url"])
            assert filtered.status_code == 200
            assert sum(tab["active"] for tab in filtered.context["order_tabs"]) == 1
        assert "Cobros aprobados" in response.content.decode()


def test_prepare_excludes_blocking_incident_and_incident_counts(order):
    order.payment_status = "approved"
    order.save()
    assert order_center_metrics()[1]["count"] == 1
    open_incident(order, "no_piece")
    cards = order_center_metrics()
    assert cards[1]["count"] == 0
    assert cards[3]["count"] == cards[3]["payment_count"] == 1


@pytest.mark.parametrize("payment", ["approved", "pending", "awaiting_manual_payment"])
def test_tabs_preserve_payment_and_counts(order, payment):
    browser, _ = staff(OPERACIONES)
    order.payment_status = payment
    order.save()
    response = browser.get(
        reverse("admin:orders_order_changelist"), {"payment_status__exact": payment}
    )
    for tab in response.context["order_tabs"]:
        assert parse_qs(urlsplit(tab["url"]).query)["payment_status__exact"] == [payment]
        filtered = browser.get(reverse("admin:orders_order_changelist") + tab["url"])
        assert filtered.context["cl"].result_count == tab["count"]


@pytest.mark.parametrize("field", ["reference", "provider_transaction_id"])
def test_search_payment_attempt(order, field):
    browser, _ = staff(OPERACIONES)
    payment = attempt(order, provider_transaction_id="wompi-search-unique")
    response = browser.get(reverse("admin:orders_order_changelist"), {"q": getattr(payment, field)})
    assert response.context["cl"].result_count == 1


def test_card_payment_summary_safety_and_full_page(order):
    browser, _ = staff(OPERACIONES)
    attempt(order, status="DECLINED", payment_method_type="CARD")
    PaymentEvent.objects.create(
        order=order,
        provider_event="transaction.updated",
        status="DECLINED",
        outcome="ignored_event",
        payload={"secret": "SENSITIVE-CARD-DATA"},
    )
    open_incident(order, "no_piece")
    html = browser.get(reverse("admin:orders_order_change", args=[order.pk])).content.decode()
    for label in [
        "Pago recibido sin pieza disponible · bloquea preparación",
        "Intentos de pago",
        f"{order.number}-01",
        "Rechazado",
        "Eventos recibidos de Wompi",
        "Imprimir / guardar PDF",
    ]:
        assert label in html
    assert "SENSITIVE-CARD-DATA" not in html
    assert "Abrir en página completa" not in html
    sections = [
        "<h3>Resumen",
        "<h3>Cliente",
        "<h3>Entrega",
        "<h3>Piezas",
        "<h3>Pagos",
        "<h3>Incidencias",
        "<h3>Estado",
        "<h3>Comunicaciones",
        "<h3>Historial",
        "<h3>Notas",
    ]
    assert [html.index(label) for label in sections] == sorted(
        html.index(label) for label in sections
    )
    listing = browser.get(reverse("admin:orders_order_changelist")).content.decode()
    assert "Último intento: rechazado" in listing
    assert "Pago recibido sin pieza disponible" in listing


def held_piece(order, piece, actor):
    order.fulfillment_status = "cancelled"
    order.save()
    OrderItem.objects.create(
        order=order, piece=piece, sku=piece.sku, name_es="Anillo", unit_price_cents=100000
    )
    piece.sale_state = "reserved"
    piece.save()
    PieceStatusChange.objects.create(
        piece=piece,
        from_state="sold",
        to_state="reserved",
        reason="admin",
        ref=order.number,
        actor=actor,
    )


def test_relist_permission_confirmation_and_audit(order, piece):
    browser, user = staff(OPERACIONES)
    held_piece(order, piece, user)
    endpoint = reverse("admin:orders-card-piece", args=[order.pk])
    assert (
        "Volver a poner a la venta"
        in browser.get(reverse("admin:orders-card", args=[order.pk])).content.decode()
    )
    assert browser.post(endpoint, {"piece_id": piece.pk, "decision": "release"}).status_code == 422
    assert (
        browser.post(
            endpoint, {"piece_id": piece.pk, "decision": "retain", "confirm": "yes"}
        ).status_code
        == 200
    )
    piece.refresh_from_db()
    assert piece.sale_state == "reserved"
    assert (
        browser.post(
            endpoint, {"piece_id": piece.pk, "decision": "release", "confirm": "yes"}
        ).status_code
        == 200
    )
    piece.refresh_from_db()
    assert piece.sale_state == "available"
    assert AuditLog.objects.filter(action="inventory.cancelled_piece_released").exists()
    assert AuditLog.objects.filter(action="inventory.cancelled_piece_retained").exists()
    assert piece.status_changes.filter(from_state="reserved", to_state="available").exists()


def test_relist_denied_and_active_reservation(order, piece):
    _, owner = staff(PROPIETARIO)
    held_piece(order, piece, owner)
    user = User.objects.create_user(username="reader", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(codename="view_order"),
        Permission.objects.get(codename="change_order"),
    )
    with pytest.raises(PermissionDenied):
        decide_cancelled_piece(piece.pk, actor=user, order_id=order.pk, release=True)
    PieceReservation.objects.create(
        piece=piece, order=order, kind="manual", expires_at=timezone.now() + timedelta(hours=1)
    )
    with pytest.raises(ValidationError):
        decide_cancelled_piece(piece.pk, actor=owner, order_id=order.pk, release=True)


def test_panel_domain_dedup_recipients_and_rollback(order):
    _, owner = staff(PROPIETARIO)
    _, operations = staff(OPERACIONES)
    _, content = staff(CONTENIDO)
    inactive = User.objects.create_user(
        username="inactive", is_superuser=True, is_staff=True, is_active=False
    )
    order_paid(order.pk)
    order_paid(order.pk)
    manual_order_created(order.pk)
    incident = open_incident(order, "no_piece")
    open_incident(order, "no_piece")
    assert AdminNotification.objects.count() == 3
    payment_notice = AdminNotification.objects.get(kind="incident")
    assert payment_notice.event_key == f"incident:{incident.pk}"
    assert set(payment_notice.receipts.values_list("user_id", flat=True)) == {owner.pk}
    assert AdminNotificationReceipt.objects.filter(user=operations).count() == 2
    assert not AdminNotificationReceipt.objects.filter(user__in=[content, inactive]).exists()
    with pytest.raises(RuntimeError), transaction.atomic():
        publish(order, "paid", "rollback")
        raise RuntimeError
    assert not AdminNotification.objects.filter(event_key="rollback").exists()


def test_panel_read_per_user_since_permissions_and_budget(order, django_assert_num_queries):
    _, owner = staff(PROPIETARIO)
    _, operations = staff(OPERACIONES)
    first = publish(order, "paid", "paid:1")
    second = publish(order, "incident", "incident:2", payment_only=True)
    with django_assert_num_queries(3):
        data = unread_data(owner, first.pk)
    assert data["count"] == 2
    assert [row["id"] for row in data["new"]] == [second.pk]
    assert order.customer_name not in str(data)
    assert order.customer_email not in str(data)
    AdminNotificationReceipt.objects.filter(user=owner, notification=first).update(
        read_at=timezone.now()
    )
    assert unread_data(owner)["count"] == 1
    assert unread_data(operations)["count"] == 1
    # Revocation hides even existing receipts.
    owner.groups.clear()
    assert unread_data(owner) is None


def test_panel_http_csrf_anonymous_methods_and_pagination(order):
    browser, user = staff(PROPIETARIO)
    notice = publish(order, "paid", "http")
    endpoint = reverse("admin-notifications-unread")
    assert Client().get(endpoint).status_code == 403
    assert browser.get(endpoint, {"since": "bad"}).status_code == 400
    assert browser.post(endpoint).status_code == 405
    assert browser.get(endpoint, {"since": notice.pk}).json()["new"] == []
    assert browser.get(reverse("admin-notifications")).status_code == 200
    strict = Client(enforce_csrf_checks=True)
    strict.cookies = browser.cookies
    assert (
        strict.post(reverse("admin-notifications-read"), {"through": notice.pk}).status_code == 403
    )
    strict.get(reverse("admin:index"))
    token = strict.cookies["csrftoken"].value
    assert (
        strict.post(
            reverse("admin-notifications-read"),
            {"through": notice.pk, "csrfmiddlewaretoken": token},
        ).status_code
        == 200
    )
    assert AdminNotificationReceipt.objects.get(user=user, notification=notice).read_at
    request = RequestFactory().get(endpoint)
    request.user = user
    assert unread(request).status_code == 200


def test_exhausted_notice_once(order, settings):
    from apps.notifications.services import deliver

    staff(PROPIETARIO)
    settings.SERTI_ORDERS_EMAIL = "owner@example.com"
    from apps.promotions.services import email_digest

    delivery = NotificationDelivery.objects.create(
        order=order,
        event="order_paid",
        channel="email",
        audience="serti",
        template="internal",
        recipient_hash=email_digest(settings.SERTI_ORDERS_EMAIL),
        idempotency_key="exhausted",
        attempts=4,
    )
    with patch("apps.notifications.adapters.send_email", side_effect=RuntimeError):
        deliver(delivery.pk)
        deliver(delivery.pk)
    assert AdminNotification.objects.filter(kind="exhausted").count() == 1


@pytest.mark.parametrize("period", ["today", "seven_days", "thirty_days", "month"])
def test_metric_period_boundaries_and_pending_exclusion(order, period):
    from apps.orders.metrics import collection_window

    now = datetime(2026, 11, 6, 20, tzinfo=UTC)
    start, _ = collection_window(period, now)
    order.payment_status = "approved"
    order.paid_at = start
    order.save()
    assert order_center_metrics(period, now)[0]["count"] == 1
    order.paid_at = start - timedelta(microseconds=1)
    order.save()
    assert order_center_metrics(period, now)[0]["count"] == 0
    order.paid_at = now + timedelta(microseconds=1)
    order.save()
    assert order_center_metrics(period, now)[0]["count"] == 0


def test_notification_endpoint_three_queries_and_twenty_items(order, django_assert_num_queries):
    browser, user = staff(OPERACIONES)
    for n in range(23):
        publish(order, "paid", f"page:{n}")
    request = RequestFactory().get(reverse("admin-notifications-unread"))
    request.user = user
    with django_assert_num_queries(3):
        response = unread(request)
    import json

    data = json.loads(response.content)
    assert data["count"] == 23
    assert len(data["items"]) == 20
    first_page = browser.get(reverse("admin-notifications"))
    second_page = browser.get(reverse("admin-notifications"), {"p": "2"})
    assert len(first_page.context["notices"]) == 20
    assert len(second_page.context["notices"]) == 3
    assert "data-notice-toggle" in first_page.content.decode()


def test_notification_direct_permissions_and_revoked_payment_access(order):
    user = User.objects.create_user(username="direct", is_staff=True)
    view = Permission.objects.get(content_type__app_label="orders", codename="view_order")
    resolve = Permission.objects.get(
        content_type__app_label="orders", codename="resolve_payment_incident"
    )
    user.user_permissions.add(view, resolve)
    publish(order, "incident", "financial", payment_only=True)
    assert unread_data(user)["count"] == 1
    user.user_permissions.remove(resolve)
    assert unread_data(user)["count"] == 0
    assert AdminNotificationReceipt.objects.filter(user=user).count() == 1
    open_incident(order, "other", notify=False)
    assert unread_data(user)["count"] == 1


def test_domain_event_notice_rolls_back_with_order(order):
    staff(PROPIETARIO)
    with pytest.raises(RuntimeError), transaction.atomic():
        order_paid(order.pk)
        open_incident(order, "no_piece")
        raise RuntimeError
    assert not AdminNotification.objects.exists()
    assert not AdminNotificationReceipt.objects.exists()


def test_retained_piece_catalog_action(order, piece):
    from django.contrib import admin

    from apps.catalog.models import Piece

    browser, user = staff(PROPIETARIO)
    held_piece(order, piece, user)
    request = RequestFactory().get("/")
    request.user = user
    model_admin = admin.site._registry[Piece]
    assert model_admin.has_detail_release_cancelled_permission(request, piece.pk)
    response = browser.get(reverse("admin:catalog_piece_change", args=[piece.pk]))
    assert "Volver a poner a la venta" in response.content.decode()


def test_full_page_stays_full_after_ajax_note(order):
    browser, _ = staff(OPERACIONES)
    response = browser.post(
        reverse("admin:orders-card-note", args=[order.pk]),
        {"text": "Nota desde página completa"},
        HTTP_X_ORDER_CARD="1",
        HTTP_X_ORDER_PAGE="1",
    )
    assert response.status_code == 200
    assert "Abrir en página completa" not in response.content.decode()
