"""Flujos HTTP reales + transporte Wompi en memoria. Ejecutar con PostgreSQL."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import timedelta
from io import BytesIO
from threading import Barrier
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connection
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.roles import CONTENIDO, PROPIETARIO
from apps.core.tests.test_dashboard_client import staff
from apps.inventory.services import release_expired_reservations
from apps.notifications.models import AdminNotification, NotificationDelivery
from apps.notifications.services import deliver
from apps.orders.api import OrderPublicThrottle
from apps.orders.exceptions import CheckoutError
from apps.orders.models import Order
from apps.orders.services import cancel_order, expire_stale_orders, transition_status
from apps.orders.tests.test_checkout import add, submit
from apps.payments.models import PaymentEvent
from apps.payments.services import confirm_manual_payment
from apps.payments.tasks import verify_wompi_event
from apps.payments.tests.test_payments import URL, event, proof
from apps.payments.wompi import WompiTransaction

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres]


class MemoryWompi:
    """Sustituye únicamente urlopen: Request, parsing y cliente siguen siendo reales."""

    def __init__(self):
        self.transactions = {}
        self.down = False
        self.calls = []

    def __call__(self, request, timeout):
        self.calls.append(request.full_url)
        assert request.get_header("Authorization").startswith("Bearer prv_test_")
        path = urlsplit(request.full_url)
        assert path.netloc in {"sandbox.wompi.co", "wompi-fake:8080"}
        if self.down:
            raise HTTPError(request.full_url, 503, "down", {}, None)
        if path.path == "/v1/transactions":
            ref = parse_qs(path.query)["reference"][0]
            data = [asdict(tx) for tx in self.transactions.values() if tx.reference == ref]
        else:
            tx = self.transactions.get(unquote(path.path.rsplit("/", 1)[1]))
            if tx is None:
                raise HTTPError(request.full_url, 404, "missing", {}, None)
            data = asdict(tx)
        response = BytesIO(json.dumps({"data": data}).encode())
        response.status = 200
        return response


@pytest.fixture(autouse=True)
def infrastructure(monkeypatch, settings):
    fake = MemoryWompi()
    monkeypatch.setattr("apps.payments.wompi.urlopen", fake)
    # Entregas se inspeccionan en cola y se procesan explícitamente, nunca por broker.
    monkeypatch.setattr("apps.notifications.services.dispatch", lambda *args: None)
    settings.SERTI_ORDERS_EMAIL = "orders@example.com"
    settings.ADMIN_2FA_REQUIRED = False
    return fake


@pytest.fixture
def order(client, piece, payload):
    assert add(client, piece).status_code == 201
    quote = client.post("/api/v1/checkout/quote", {"wants_certificate": False}, format="json")
    assert quote.status_code == 200
    assert "wompi" in quote.data["payment_channels"]
    result = submit(client, payload)
    assert result.status_code == 201
    return Order.objects.get(public_token=result.data["public_token"])


def send(client, order, fake, status="APPROVED", body=None):
    attempt = order.payment_attempts.order_by("-sequence").first()
    tx = WompiTransaction(
        f"tx-{attempt.reference}", attempt.reference, status, attempt.amount_cents, "COP", "PSE"
    )
    fake.transactions[tx.id] = tx
    response = client.post(URL, body or event(tx), format="json")
    assert response.status_code == 200
    return tx


def public(client, order):
    return client.get(f"/api/v1/orders/{order.public_token}")


def request_for(user):
    request = RequestFactory().post("/")
    request.user = user
    return request


def assert_paid(order):
    order.refresh_from_db()
    assert order.payment_status == "approved"
    assert order.items.get().piece.sale_state == "sold"
    assert order.reservations.filter(status="converted").count() == 1
    assert order.deliveries.filter(event="order_paid", channel="email").count() == 2
    assert AdminNotification.objects.filter(order=order, kind="paid").count() == 1


def test_purchase(client, order, infrastructure):
    send(client, order, infrastructure)
    assert_paid(order)
    assert infrastructure.calls
    assert public(client, order).data["payment"]["status"] == "approved"


def test_pending_then_paid_once(client, order, infrastructure):
    for _ in range(3):
        send(client, order, infrastructure, "PENDING")
    assert order.deliveries.filter(event="order_received").count() == 1
    assert public(client, order).data["payment"]["status"] == "pending"
    for _ in range(3):
        send(client, order, infrastructure)
    assert_paid(order)
    assert order.deliveries.filter(event="order_received").count() == 1


def test_declined_retry(client, order, infrastructure):
    send(client, order, infrastructure, "DECLINED")
    result = client.post(
        f"/api/v1/orders/{order.public_token}/payment-attempts",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="11111111-1111-4111-8111-111111111111",
    )
    assert result.status_code in (200, 201)
    assert order.payment_attempts.order_by("-sequence").first().reference.endswith("-02")
    send(client, order, infrastructure)
    assert_paid(order)


def test_duplicate_webhook(client, order, infrastructure):
    for _ in range(3):
        send(client, order, infrastructure)
    assert_paid(order)
    assert order.items.get().piece.status_changes.filter(to_state="sold").count() == 1
    assert PaymentEvent.objects.filter(order=order, outcome="duplicate").count() == 2


def test_signatures_and_manipulated_reference(client, order, infrastructure):
    attempt = order.payment_attempts.get()
    tx = WompiTransaction(
        "bad-signature", attempt.reference, "APPROVED", attempt.amount_cents, "COP"
    )
    infrastructure.transactions[tx.id] = tx
    body = event(tx)
    body["signature"]["checksum"] = "0" * 64
    assert client.post(URL, body, format="json").status_code == 200
    assert not infrastructure.calls
    order.refresh_from_db()
    assert order.payment_status == "pending" and not order.deliveries.exists()
    body = event(replace(tx, reference="manipulada"))
    assert client.post(URL, body, format="json").status_code == 200
    order.refresh_from_db()
    assert order.payment_status == "pending"
    assert order.incidents.filter(kind="suspicious").exists()
    assert PaymentEvent.objects.filter(outcome="mismatch").exists()


def test_api_down_persists_queues_and_recovers(client, order, infrastructure):
    infrastructure.down = True
    with patch("apps.payments.tasks.verify_wompi_event.delay") as queue:
        send(client, order, infrastructure)
    receipt = PaymentEvent.objects.get(provider_event="transaction.updated.received")
    queue.assert_called_once_with(receipt.pk)
    order.refresh_from_db()
    assert order.payment_status == "pending"
    infrastructure.down = False
    verify_wompi_event.run(receipt.pk)
    assert_paid(order)


def test_smtp_failure_and_card_resend(client, order, infrastructure):
    send(client, order, infrastructure)
    delivery = order.deliveries.get(event="order_paid", channel="email", audience="customer")
    with patch("django.core.mail.message.EmailMultiAlternatives.send", side_effect=OSError("SMTP")):
        deliver(delivery.pk)
    delivery.refresh_from_db()
    assert delivery.status == "failed" and delivery.next_attempt_at > timezone.now()
    assert_paid(order)
    browser, _ = staff(PROPIETARIO)
    response = browser.post(
        reverse("admin:orders-card-communication", args=[order.pk]),
        {"delivery_id": delivery.pk, "action": "resend", "confirm": "yes"},
    )
    assert response.status_code == 200
    deliver(delivery.pk)
    delivery.refresh_from_db()
    assert delivery.status == "sent"
    assert_paid(order)


def test_whatsapp_failure_isolated(client, order, infrastructure, settings):
    # Real provider path (not the "log" simulation, which is recorded as skipped).
    settings.WHATSAPP_PROVIDER = "cloud"
    settings.WHATSAPP_ACCESS_TOKEN = "test-token"  # noqa: S105
    settings.WHATSAPP_PHONE_NUMBER_ID = "123456"
    settings.WHATSAPP_ORDERS_RECIPIENT = "573001112233"
    settings.WHATSAPP_TEMPLATE_NEW_ORDER = "nuevo_pedido"
    send(client, order, infrastructure)
    delivery = order.deliveries.get(event="order_paid", channel="whatsapp")
    with patch("apps.notifications.adapters.send_whatsapp", side_effect=OSError):
        deliver(delivery.pk)
    delivery.refresh_from_db()
    assert delivery.status == "failed"
    for email in order.deliveries.filter(event="order_paid", channel="email"):
        deliver(email.pk)
    assert order.deliveries.filter(channel="email", status="sent").count() == 2
    assert_paid(order)


def test_unauthorized_and_invalid_transition(client, order, infrastructure):
    send(client, order, infrastructure)
    browser, _ = staff(CONTENIDO)
    url = reverse("admin:orders-card-status", args=[order.pk])
    assert browser.post(url, {"target": "preparing"}).status_code == 403
    # Django admin redirects anonymous HTTP clients to login; service denies with 403 semantics.
    assert client.post(url, {"target": "preparing"}).status_code == 302
    with pytest.raises(PermissionDenied):
        transition_status(
            order, "fulfillment_status", "preparing", request=request_for(AnonymousUser())
        )
    browser, owner = staff(PROPIETARIO)
    with pytest.raises(CheckoutError):
        transition_status(order, "fulfillment_status", "delivered", request=request_for(owner))
    assert (
        browser.post(url, {"target": "delivered", "expected_status": "unfulfilled"}).status_code
        == 422
    )


def parallel(run):
    barrier = Barrier(2)

    def worker(index):
        close_old_connections()
        try:
            return run(index, barrier)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        return list(pool.map(worker, range(2)))


def test_two_administrators(client, order, infrastructure):
    send(client, order, infrastructure)
    _, owner = staff(PROPIETARIO)
    other = User.objects.create_user(username="second-admin", is_staff=True)
    other.groups.set(owner.groups.all())
    admin_ids = [owner.pk, other.pk]

    def run(index, barrier):
        actor = User.objects.get(pk=admin_ids[index])
        local = Order.objects.get(pk=order.pk)
        barrier.wait(timeout=10)
        try:
            transition_status(
                local,
                "fulfillment_status",
                "preparing",
                request=request_for(actor),
                expected_status="unfulfilled",
                notify=False,
            )
            return "ok"
        except ValidationError as exc:
            return " ".join(exc.messages)

    assert sorted(parallel(run)) == ["El pedido cambió, recarga.", "ok"]
    assert order.status_changes.filter(to_state="preparing").count() == 1


def test_guest_tracking_privacy_expiry_and_throttle(client, order, monkeypatch):
    _, owner = staff(PROPIETARIO)
    order.notes.create(author=owner, text="INTERNO SECRETO")
    response = public(client, order)
    assert response.status_code == 200
    for secret in (
        order.customer_email,
        order.customer_phone,
        order.shipping_address_line,
        "INTERNO SECRETO",
    ):
        assert secret not in json.dumps(response.data, default=str)
    assert client.get("/api/v1/orders/incorrecto").status_code == 404
    Order.objects.filter(pk=order.pk).update(
        payment_status="expired", reservation_expires_at=timezone.now() - timedelta(days=31)
    )
    assert public(client, order).status_code == 404
    from django.core.cache import cache

    cache.clear()
    monkeypatch.setattr(OrderPublicThrottle, "get_rate", lambda self: "1/min")
    assert public(client, order).status_code == 404
    assert public(client, order).status_code == 429


def test_two_buyers_only_one_reservation(piece, payload):
    buyers = [APIClient(), APIClient()]
    for browser in buyers:
        assert add(browser, piece).status_code == 201

    def run(index, barrier):
        barrier.wait(timeout=10)
        return submit(buyers[index], payload).status_code

    assert sorted(parallel(run)) == [201, 409]
    assert Order.objects.count() == 1
    assert piece.reservations.filter(status="active").count() == 1


def test_late_payment_piece_already_sold(client, order, piece, payload, infrastructure):
    past = timezone.now() - timedelta(minutes=1)
    order.reservations.update(expires_at=past)
    Order.objects.filter(pk=order.pk).update(reservation_expires_at=past)
    assert release_expired_reservations() == 1
    assert expire_stale_orders() == 1
    other = APIClient()
    assert add(other, piece).status_code == 201
    assert submit(other, payload).status_code == 201
    second = Order.objects.exclude(pk=order.pk).get()
    send(other, second, infrastructure)
    send(client, order, infrastructure)
    order.refresh_from_db()
    assert order.incidents.filter(kind="no_piece").exists()
    assert order.payment_status == "approved"
    assert not order.reservations.filter(status="converted").exists()
    assert piece.status_changes.filter(to_state="sold").count() == 1


@pytest.mark.parametrize("paid_first", [False, True])
def test_cancel_and_late_payment(client, order, infrastructure, paid_first):
    _, owner = staff(PROPIETARIO)
    if paid_first:
        send(client, order, infrastructure)
    cancel_order(
        order, actor=owner, reason="Cliente cancela", notify=False, expected_status="unfulfilled"
    )
    if not paid_first:
        send(client, order, infrastructure)
    order.refresh_from_db()
    assert order.fulfillment_status == "cancelled"
    assert order.incidents.filter(
        kind="refund_pending" if paid_first else "cancelled_payment"
    ).exists()
    assert order.items.get().piece.sale_state != "sold"


def test_apply_failure_rolls_back_then_retry(client, order, infrastructure):
    # Failure after inventory, status and durable notices have been written.
    from apps.payments.services import _approve

    def fail(*args, **kwargs):
        _approve(*args, **kwargs)
        raise RuntimeError("forced after approval")

    with patch("apps.payments.services._approve", side_effect=fail):
        attempt = order.payment_attempts.get()
        tx = WompiTransaction(
            "rollback", attempt.reference, "APPROVED", attempt.amount_cents, "COP"
        )
        infrastructure.transactions[tx.id] = tx
        assert client.post(URL, event(tx), format="json").status_code == 503
    order.refresh_from_db()
    assert order.payment_status == "pending" and order.paid_at is None
    assert order.items.get().piece.sale_state == "reserved"
    assert order.payment_attempts.get().status == "PENDING"
    assert order.reservations.get().status == "active"
    assert not order.items.get().piece.status_changes.filter(to_state="sold").exists()
    assert not PaymentEvent.objects.filter(outcome="applied").exists()
    assert not AdminNotification.objects.filter(order=order).exists()
    assert not NotificationDelivery.objects.filter(order=order).exists()
    assert client.post(URL, event(tx), format="json").status_code == 200
    assert_paid(order)


def test_no_manual_confirmation_for_wompi(order):
    browser, owner = staff(PROPIETARIO)
    with pytest.raises(CheckoutError):
        confirm_manual_payment(
            order, actor=owner, reference="manual", proof=proof(), request=request_for(owner)
        )
    response = browser.post(
        reverse("admin:orders-confirm-manual", args=[order.pk]),
        {"reference": "manual", "proof": proof()},
    )
    assert response.status_code == 200 and response.context_data["form"].errors
    order.refresh_from_db()
    assert order.payment_status == "pending"
    assert not order.payment_attempts.filter(channel="manual").exists()


def test_receipt_or_queue_failure_returns_503(client, order, infrastructure):
    from django.db import DatabaseError

    attempt = order.payment_attempts.get()
    tx = WompiTransaction("unpersisted", attempt.reference, "APPROVED", attempt.amount_cents, "COP")
    with patch("apps.payments.api.record_event", side_effect=DatabaseError):
        assert client.post(URL, event(tx), format="json").status_code == 503
    assert not PaymentEvent.objects.exists()
    infrastructure.down = True
    with patch("apps.payments.tasks.verify_wompi_event.delay", side_effect=OSError):
        assert client.post(URL, event(tx), format="json").status_code == 503
    order.refresh_from_db()
    assert order.payment_status == "pending"


def test_e2e_session_authenticates_without_password(settings):
    from io import StringIO

    from django.core.management import call_command

    settings.DEBUG = True
    settings.ADMIN_2FA_REQUIRED = False
    output = StringIO()
    call_command("e2e_admin_session", stdout=output)
    data = json.loads(output.getvalue())
    browser = APIClient()
    browser.cookies[data["name"]] = data["value"]
    assert browser.get(data["admin_url"]).status_code == 200
    actor = User.objects.get(username__startswith="e2e-")
    assert not actor.has_usable_password()
    assert actor.has_perm("orders.change_fulfillment")
