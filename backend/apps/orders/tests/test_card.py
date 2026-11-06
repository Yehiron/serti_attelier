from datetime import datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.roles import CONTENIDO, OPERACIONES, PROPIETARIO
from apps.core.formatting import BOGOTA
from apps.core.models import Municipality
from apps.core.tests.test_dashboard_client import staff
from apps.notifications.models import NotificationDelivery
from apps.notifications.rendering import render_email
from apps.orders.models import Order, OrderItem

pytestmark = pytest.mark.django_db


@pytest.fixture
def order(payload) -> Order:
    return Order.objects.create(
        number="SRT-OP",
        idempotency_key=uuid4(),
        request_hash="x",
        customer_name="Cliente",
        customer_email="client@example.com",
        customer_phone="+573001234567",
        email_hash="x",
        shipping_address_line="Calle 123",
        shipping_municipality=Municipality.objects.get(pk="05001"),
        subtotal_cents=100000,
        total_cents=100000,
        payment_channel="wompi",
        terms_version=1,
        privacy_version=1,
        privacy_consent_at=timezone.now(),
    )


def card_url(order):
    return reverse("admin:orders-card", args=[order.pk])


def post_data(order, **kwargs):
    return {
        "target": "preparing",
        "expected_status": order.fulfillment_status,
        "notify": "on",
        **kwargs,
    }


@pytest.mark.parametrize("role", [PROPIETARIO, OPERACIONES, CONTENIDO])
def test_card_permissions_and_versions(order, piece, role):
    browser, _ = staff(role)
    OrderItem.objects.create(
        order=order,
        piece=piece,
        sku="SNAPSHOT",
        name_es="Anillo único",
        name_en="Unique ring",
        unit_price_cents=100000,
    )
    for suffix in ("", "?full=1", "?print=1"):
        response = browser.get(card_url(order) + suffix)
        assert response.status_code == (403 if role == CONTENIDO else 200)
        if role != CONTENIDO:
            html = response.content.decode()
            for text in (
                order.number,
                order.customer_name,
                order.customer_email,
                order.shipping_address_line,
                "Anillo único",
                "SNAPSHOT",
                "TOTAL",
            ):
                assert text in html
            if suffix == "?print=1":
                assert f"<title>Pedido {order.number}</title>" in html
                assert "order-print.js" in html and "wordmark-wine" in html
                assert 'id="header"' not in html
    missing = browser.get(reverse("admin:orders-card", args=[999999]))
    assert missing.status_code == (403 if role == CONTENIDO else 404)


@pytest.mark.parametrize("notify", [True, False])
@pytest.mark.parametrize(
    "current,target",
    [
        ("unfulfilled", "preparing"),
        ("preparing", "shipped"),
        ("shipped", "delivered"),
        ("preparing", "cancelled"),
        ("delivered", "returned"),
    ],
)
def test_card_transition(order, notify, current, target, django_capture_on_commit_callbacks):
    browser, _ = staff(OPERACIONES)
    order.payment_status = "approved"
    order.fulfillment_status = current
    order.save()
    with (
        patch("apps.notifications.services.dispatch"),
        django_capture_on_commit_callbacks(execute=True),
    ):
        response = browser.post(
            reverse("admin:orders-card-status", args=[order.pk]),
            post_data(
                order, target=target, carrier="Transportadora", notify="on" if notify else ""
            ),
            HTTP_X_ORDER_CARD="1",
        )
    assert response.status_code == 200
    assert response["X-Order-Updated"] == "1"
    order.refresh_from_db()
    assert order.fulfillment_status == target
    notified = notify and target != "returned"
    assert NotificationDelivery.objects.count() == int(notified)
    if notified:
        assert NotificationDelivery.objects.get().event == f"order_{target}"
    assert ("encolado" if notified else "Sin notificar") in order.status_changes.get().note


@pytest.mark.parametrize(
    "target,current,paid,extra",
    [
        ("delivered", "unfulfilled", "approved", {}),
        ("preparing", "unfulfilled", "pending", {}),
        ("shipped", "preparing", "approved", {}),
        (
            "shipped",
            "preparing",
            "approved",
            {"carrier": "Correo", "tracking_url": "http://example.com"},
        ),
    ],
)
def test_card_invalid_transition(order, target, current, paid, extra):
    browser, _ = staff(OPERACIONES)
    order.fulfillment_status = current
    order.payment_status = paid
    order.save()
    response = browser.post(
        reverse("admin:orders-card-status", args=[order.pk]),
        post_data(order, target=target, **extra),
        HTTP_X_ORDER_CARD="1",
    )
    assert response.status_code == 422
    assert not order.status_changes.exists() and not NotificationDelivery.objects.exists()
    order.refresh_from_db()
    assert order.fulfillment_status == current


def test_card_stale_state_and_no_email(order, django_capture_on_commit_callbacks):
    browser, _ = staff(OPERACIONES)
    order.payment_status = "approved"
    order.customer_email = ""
    order.save()
    endpoint = reverse("admin:orders-card-status", args=[order.pk])
    assert browser.post(endpoint, post_data(order, expected_status="preparing")).status_code == 422
    with django_capture_on_commit_callbacks(execute=True):
        response = browser.post(endpoint, post_data(order))
    assert response.status_code == 200
    assert not NotificationDelivery.objects.exists()


def test_card_permission_csrf_methods(order):
    browser, user = staff(CONTENIDO)
    endpoint = reverse("admin:orders-card-status", args=[order.pk])
    assert browser.post(endpoint, post_data(order)).status_code == 403
    browser, user = staff(OPERACIONES)
    user.groups.clear()
    user.user_permissions.add(Permission.objects.get(codename="view_order"))
    assert browser.get(card_url(order)).status_code == 200
    assert "data-status-form" not in browser.get(card_url(order)).content.decode()
    assert browser.post(endpoint, post_data(order)).status_code == 403
    browser, _ = staff(PROPIETARIO)
    protected = Client(enforce_csrf_checks=True)
    protected.cookies = browser.cookies
    assert protected.post(endpoint, post_data(order)).status_code == 403
    page = protected.get(card_url(order))
    token = protected.cookies["csrftoken"].value
    assert page.status_code == 200
    assert (
        protected.post(
            endpoint, post_data(order, target="cancelled"), HTTP_X_CSRFTOKEN=token
        ).status_code
        == 200
    )
    assert browser.get(endpoint).status_code == 405
    assert browser.post(card_url(order)).status_code == 405


@pytest.mark.parametrize("locale", ["es", "en"])
@pytest.mark.parametrize(
    "event", ["order_preparing", "order_delivered", "order_cancelled", "order_shipped"]
)
def test_new_email_events(order, piece, locale, event):
    OrderItem.objects.create(
        order=order,
        piece=piece,
        sku=piece.sku,
        name_es="Anillo",
        name_en="Ring",
        unit_price_cents=100000,
    )
    delivery = NotificationDelivery(event=event, locale=locale, audience="customer", template=event)
    content = render_email(delivery, order)
    for text in (content.subject, content.html, content.text):
        assert order.number in text
    for body in (content.html, content.text):
        assert ("Ring" if locale == "en" else "Anillo") in body


def test_list_pagination_tabs_search_and_check(order):
    browser, _ = staff(OPERACIONES)
    for index in range(23):
        clone = Order.objects.get(pk=order.pk)
        clone.pk = None
        clone.number = f"SRT-CARD-{index}"
        clone.public_token = str(uuid4())
        clone.idempotency_key = uuid4()
        clone.payment_status = "approved"
        clone.fulfillment_status = [
            "unfulfilled",
            "preparing",
            "shipped",
            "delivered",
            "cancelled",
            "returned",
        ][index % 6]
        clone.save()
    endpoint = reverse("admin:orders_order_changelist")
    response = browser.get(endpoint)
    assert response.status_code == 200
    assert len(response.context["cl"].result_list) == 20
    assert response.context["cl"].result_count == 24
    page2 = browser.get(endpoint, {"p": 2})
    assert len(page2.context["cl"].result_list) == 4
    assert "Página 2 de 2" in page2.content.decode()
    for tab in response.context["order_tabs"]:
        filtered = browser.get(endpoint + tab["url"])
        assert filtered.status_code == 200
        assert filtered.context["cl"].result_count == tab["count"]
        assert sum(item["active"] for item in filtered.context["order_tabs"]) == 1
    shared = browser.get(endpoint, {"pedido": order.pk, "q": "SRT-CARD"})
    assert shared.status_code == 200 and shared.context["cl"].result_count == 23
    assert all("q=SRT-CARD" in tab["url"] for tab in shared.context["order_tabs"])
    call_command("check")


def test_date_range_includes_end_of_day(order):
    browser, _ = staff(OPERACIONES)
    Order.objects.filter(pk=order.pk).update(
        created_at=datetime(2026, 10, 2, 23, 50, tzinfo=BOGOTA)
    )
    response = browser.get(
        reverse("admin:orders_order_changelist"),
        {"created_at_from": "2026-10-02", "created_at_to": "2026-10-02"},
    )
    assert response.status_code == 200
    assert response.context["cl"].result_count == 1


def test_list_total_certificate_coupon_attention_filters(order):
    browser, _ = staff(OPERACIONES)
    order.wants_certificate = True
    order.needs_attention = True
    order.save()
    endpoint = reverse("admin:orders_order_changelist")
    for query, expected in [
        ({"total_cents_from": "900", "total_cents_to": "1100"}, 1),
        ({"total_cents_from": "1001"}, 0),
        ({"wants_certificate__exact": "1"}, 1),
        ({"needs_attention__exact": "1"}, 1),
        ({"has_coupon": "yes"}, 0),
        ({"has_coupon": "no"}, 1),
    ]:
        response = browser.get(endpoint, query)
        assert response.status_code == 200
        assert response.context["cl"].result_count == expected


def test_anonymous_cannot_read_or_update(order):
    browser = Client()
    assert browser.get(card_url(order)).status_code == 302
    assert (
        browser.post(
            reverse("admin:orders-card-status", args=[order.pk]), post_data(order)
        ).status_code
        == 302
    )


def test_print_includes_complete_notes_without_controls(order):
    from apps.orders.models import OrderNote, OrderStatusChange

    browser, user = staff(OPERACIONES)
    OrderNote.objects.create(order=order, author=user, text="Nota privada de la tienda")
    OrderStatusChange.objects.create(
        order=order,
        field="fulfillment_status",
        from_state="unfulfilled",
        to_state="preparing",
        note="Nota privada del cambio",
        actor=user,
    )
    printed = browser.get(card_url(order) + "?print=1").content.decode()
    assert "Nota privada de la tienda" in printed and "Nota privada del cambio" in printed
    assert "<form" not in printed
    assert "<button" not in printed and "data-status-form" not in printed
    card = browser.get(card_url(order)).content.decode()
    assert "Nota privada de la tienda" in card and "Nota privada del cambio" in card


def test_list_has_only_view_button(order):
    from django.contrib import admin

    browser, _ = staff(OPERACIONES)
    response = browser.get(reverse("admin:orders_order_changelist"))
    assert response.status_code == 200
    assert admin.site._registry[Order].actions_row == ()
    assert response.context["cl"].model_admin.get_actions_row(response.wsgi_request) == []
    assert "Ver pedido" in response.content.decode()


@pytest.mark.parametrize("role", [OPERACIONES, CONTENIDO])
def test_change_view_complete(order, piece, role):
    from apps.orders.models import OrderNote, OrderStatusChange

    browser, user = staff(role)
    OrderItem.objects.create(
        order=order, piece=piece, sku="FICHA", name_es="Pieza completa", unit_price_cents=100000
    )
    OrderNote.objects.create(order=order, author=user, text="Nota de la ficha")
    OrderStatusChange.objects.create(
        order=order,
        field="payment_status",
        from_state="pending",
        to_state="approved",
        note="Pago revisado",
    )
    response = browser.get(reverse("admin:orders_order_change", args=[order.pk]))
    assert response.status_code == (403 if role == CONTENIDO else 200)
    if role == OPERACIONES:
        html = response.content.decode()
        for text in (
            "Pieza completa",
            "FICHA",
            "Nota de la ficha",
            "Pago revisado",
            "Migas de pan",
            reverse("admin:catalog_piece_change", args=[piece.pk]),
        ):
            assert text in html
    missing = browser.get(reverse("admin:orders_order_change", args=[999999]))
    assert missing.status_code == (403 if role == CONTENIDO else 404)


def test_card_add_note_permissions_csrf_and_validation(order):
    from apps.audit.models import AuditLog

    browser, user = staff(OPERACIONES)
    endpoint = reverse("admin:orders-card-note", args=[order.pk])
    assert browser.get(endpoint).status_code == 405
    empty = browser.post(endpoint, {"text": "  "}, HTTP_X_ORDER_CARD="1")
    assert empty.status_code == 422 and "Escribe una nota." in empty.content.decode()
    protected = Client(enforce_csrf_checks=True)
    protected.cookies = browser.cookies
    assert protected.post(endpoint, {"text": "Nota"}).status_code == 403
    protected.get(card_url(order))
    response = protected.post(
        endpoint,
        {"text": "  Nota nueva  "},
        HTTP_X_CSRFTOKEN=protected.cookies["csrftoken"].value,
        HTTP_X_ORDER_CARD="1",
    )
    assert response.status_code == 200 and "Nota nueva" in response.content.decode()
    assert order.notes.get().text == "Nota nueva"
    assert order.notes.get().author == user
    assert AuditLog.objects.filter(action="orders.note_added").exists()
    user.groups.clear()
    user.user_permissions.add(Permission.objects.get(codename="view_order"))
    assert browser.post(endpoint, {"text": "Prohibida"}).status_code == 403
    browser, _ = staff(CONTENIDO)
    assert browser.post(endpoint, {"text": "Prohibida"}).status_code == 403
    assert order.notes.count() == 1


def test_card_manual_payment_and_certificate_links(order):
    browser, _ = staff(PROPIETARIO)
    order.payment_status = "awaiting_manual_payment"
    order.save()
    manual = reverse("admin:orders-confirm-manual", args=[order.pk])
    assert manual in browser.get(card_url(order)).content.decode()
    assert browser.get(manual).status_code == 200
    order.payment_status = "approved"
    order.wants_certificate = True
    order.save()
    certificate = reverse("admin:orders-certificate", args=[order.pk])
    assert certificate in browser.get(card_url(order)).content.decode()
    assert browser.get(certificate).status_code == 200


def test_card_state_select_offers_the_allowed_targets(order):
    from apps.orders.forms import CardFulfillmentForm

    order.payment_status = "approved"
    order.save(update_fields=["payment_status"])
    html = str(CardFulfillmentForm(order=order)["target"])
    assert 'value="preparing"' in html
    assert 'value="cancelled"' in html
    assert 'value="shipped"' not in html
