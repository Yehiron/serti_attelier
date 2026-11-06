from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from io import BytesIO
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.admin.sites import site
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import RequestFactory, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.catalog.models import Piece
from apps.inventory.services import release_reservation
from apps.orders.exceptions import CheckoutError
from apps.orders.models import Order
from apps.orders.services import expire_stale_orders
from apps.payments.admin import PaymentAttemptAdmin
from apps.payments.models import PaymentAttempt, PaymentEvent
from apps.payments.services import apply_transaction, confirm_manual_payment, create_wompi_attempt
from apps.payments.tasks import reconcile_pending
from apps.payments.wompi import (
    WompiClient,
    WompiTransaction,
    checkout_fields,
    event_checksum,
    integrity_signature,
    verify_event,
)
from apps.promotions.models import Coupon, CouponRedemption

pytestmark = pytest.mark.django_db
URL = "/api/v1/payments/wompi/events"


def tx_for(order: Order, status: str = "APPROVED", **kwargs: Any) -> WompiTransaction:
    attempt = order.payment_attempts.order_by("-sequence").get()
    return WompiTransaction(
        "tx-123", attempt.reference, status, attempt.amount_cents, "COP", **kwargs
    )


def event(tx: WompiTransaction) -> dict[str, Any]:
    from dataclasses import asdict

    body: dict[str, Any] = {
        "event": "transaction.updated",
        "data": {"transaction": {**asdict(tx), "customer_data": {"email": "secret@example.com"}}},
        "timestamp": 123,
        "signature": {
            "properties": ["transaction.id", "transaction.status", "transaction.amount_in_cents"]
        },
    }
    body["signature"]["checksum"] = event_checksum(body)
    return body


@override_settings(WOMPI_INTEGRITY_SECRET="secret")
@pytest.mark.parametrize("expiration", ["", "2026-10-26T20:28:50.000Z"])
def test_integrity(expiration: str) -> None:
    expected = (
        "d6be37ffacdf58b9c52d7edc2c3d72c9066d5618ddec84423ad741c06a3a50ab"
        if expiration
        else "7fa23b84b52677d6848c96954ad5db8093158e89faecdb70d30824c370cdcb46"
    )
    assert integrity_signature("SRT-000123-01", 4000, "COP", expiration) == expected


@override_settings(WOMPI_EVENTS_SECRET="prod_events_OcHnIzeBl5socpwByQ4hA52Em3USQ93Z")
def test_official_event_vector() -> None:
    body: dict[str, Any] = {
        "data": {
            "transaction": {
                "id": "1234-1610641025-49201",
                "status": "APPROVED",
                "amount_in_cents": 4490000,
            }
        },
        "timestamp": 1530291411,
        "signature": {
            "properties": ["transaction.id", "transaction.status", "transaction.amount_in_cents"],
            "checksum": "3476DDA50F64CD7CBD160689640506FEBEA93239BC524FC0469B2C68A3CC8BD0",
        },
    }
    # The supplied official vector is inconsistent with its stated inputs.
    assert not verify_event(body)
    assert (
        event_checksum(body) == "5a18ec5e8fdb7df463e9f94774cba8f583ba21bd04a09ceff2ea68a4bc0aefbe"
    )
    body["signature"]["checksum"] = event_checksum(body)
    assert verify_event(body)


@override_settings(WOMPI_EVENTS_SECRET="secret")
def test_dynamic_properties(order: Order) -> None:
    body = event(tx_for(order))
    body["signature"]["properties"] = [
        "transaction.currency",
        "transaction.amount_in_cents",
        "transaction.status",
        "transaction.id",
    ]
    body["signature"]["checksum"] = event_checksum(body).upper()
    assert verify_event(body)
    body["signature"]["properties"].append("transaction.missing")
    assert not verify_event(body)


@override_settings(WOMPI_PUBLIC_KEY="pub_test_x", WOMPI_INTEGRITY_SECRET="test_integrity_secret")
def test_checkout_and_reload(order: Order, client: APIClient) -> None:
    first = order.payment_attempts.get()
    assert create_wompi_attempt(order) == first
    fields = checkout_fields(first)
    assert len(fields) == 7 and all(isinstance(v, str) for v in fields.values())
    assert fields["expiration-time"].endswith("Z")
    assert fields["redirect-url"].endswith(f"/es/pedido/{order.public_token}")
    prefilled = checkout_fields(first, include_customer=True)
    assert len(prefilled) == 14 and prefilled["shipping-address:country"] == "CO"
    detail = client.get(f"/api/v1/orders/{order.public_token}").data
    assert detail["wompi"]["fields"] == fields and detail["payment"]["can_retry"] is False


def test_public_order_view_never_exposes_customer_data(order: Order, client: APIClient) -> None:
    # The order link alone must not reveal PII, even though Wompi prefill needs it once.
    detail = str(client.get(f"/api/v1/orders/{order.public_token}").data)
    for value in (order.customer_email, order.customer_phone, order.shipping_address_line):
        assert value not in detail
    assert "customer-data" not in detail and "shipping-address" not in detail


@override_settings(WOMPI_PUBLIC_KEY="", WOMPI_INTEGRITY_SECRET="")
def test_unavailable(order: Order, client: APIClient) -> None:
    data = client.get(f"/api/v1/orders/{order.public_token}").data
    assert data["wompi"] is None and data["payment_unavailable"]


@override_settings(WOMPI_EVENTS_SECRET="secret")
def test_approved_duplicate_coupon_hook(
    order: Order, client: APIClient, django_capture_on_commit_callbacks: Any
) -> None:
    coupon = Coupon.objects.create(code="PAY", kind="percent", value=10)
    order.coupon = coupon
    order.save(update_fields=["coupon"])
    body = event(tx_for(order))
    with (
        patch("apps.orders.events.order_paid") as hook,
        patch("apps.payments.wompi.WompiClient.get_transaction", return_value=tx_for(order)),
        django_capture_on_commit_callbacks(execute=True),
    ):
        assert client.post(URL, body, format="json").status_code == 200
        assert client.post(URL, body, format="json").status_code == 200
    hook.assert_called_once_with(order.pk)
    order.refresh_from_db()
    assert order.payment_status == "approved" and order.paid_at
    assert order.items.get().piece.sale_state == "sold"
    assert CouponRedemption.objects.filter(order=order).count() == 1
    assert list(PaymentEvent.objects.values_list("outcome", flat=True)) == [
        "ignored_event",
        "applied",
        "ignored_event",
        "duplicate",
    ]
    assert "secret@example.com" not in str(
        list(PaymentEvent.objects.values_list("payload", flat=True))
    )


@override_settings(WOMPI_EVENTS_SECRET="secret")
def test_rejected_unknown_ignored(order: Order, client: APIClient) -> None:
    body = event(tx_for(order))
    body["signature"]["checksum"] = "bad"
    assert client.post(URL, body, format="json").status_code == 200
    assert PaymentEvent.objects.get().outcome == "rejected_checksum"
    unknown = event(replace(tx_for(order), reference="missing"))
    with patch(
        "apps.payments.wompi.WompiClient.get_transaction",
        return_value=replace(tx_for(order), reference="missing"),
    ):
        assert client.post(URL, unknown, format="json").status_code == 200
    assert PaymentEvent.objects.latest("pk").outcome == "unknown_reference"
    body = event(tx_for(order))
    body["event"] = "other"
    assert client.post(URL, body, format="json").status_code == 200
    assert PaymentEvent.objects.latest("pk").outcome == "ignored_event"
    order.refresh_from_db()
    assert order.payment_status == "pending"


@pytest.mark.parametrize("field,value", [("amount_in_cents", 1), ("currency", "USD")])
def test_mismatch(order: Order, field: str, value: Any) -> None:
    assert (
        apply_transaction(replace(tx_for(order), **{field: value}), source="webhook") == "mismatch"
    )
    order.refresh_from_db()
    assert order.needs_attention and order.payment_status == "pending"


@pytest.mark.parametrize("status", ["DECLINED", "ERROR", "VOIDED"])
def test_retry(order: Order, client: APIClient, status: str) -> None:
    apply_transaction(tx_for(order, status), source="webhook")
    url = f"/api/v1/orders/{order.public_token}/payment-attempts"
    key = str(uuid4())
    assert client.post(url, {}, format="json", HTTP_IDEMPOTENCY_KEY=key).status_code == 201
    assert client.post(url, {}, format="json", HTTP_IDEMPOTENCY_KEY=key).status_code == 201
    assert order.payment_attempts.count() == 2
    second = order.payment_attempts.get(sequence=2)
    assert second.reference.endswith("-02")
    approved = WompiTransaction("tx-2", second.reference, "APPROVED", second.amount_cents, "COP")
    assert apply_transaction(approved, source="webhook") == "applied"
    assert (
        client.post(url, {}, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid4())).data["code"]
        == "payment_not_retryable"
    )


@pytest.mark.parametrize("state", ["pending", "approved", "expired", "manual"])
def test_not_retryable(order: Order, state: str) -> None:
    if state == "manual":
        order.payment_channel = "manual"
    else:
        order.payment_status = state
    order.save()
    with pytest.raises(CheckoutError, match="No se pudo"):
        create_wompi_attempt(order, retry=True)


def test_voided(order: Order) -> None:
    tx = tx_for(order)
    apply_transaction(tx, source="webhook")
    apply_transaction(replace(tx, status="VOIDED"), source="webhook")
    order.refresh_from_db()
    assert order.payment_status == "voided" and order.needs_attention
    assert order.items.get().piece.sale_state == "sold"


@pytest.mark.parametrize("taken", [False, True])
def test_late_approval(order: Order, taken: bool) -> None:
    release_reservation(order.reservations.get().pk, reason="reservation_expired")
    expire_stale_orders()
    if taken:
        Piece.objects.filter(pk=order.items.get().piece_id).update(sale_state="sold")
    assert apply_transaction(tx_for(order), source="webhook") == "applied"
    order.refresh_from_db()
    assert order.payment_status == "approved" and order.needs_attention == taken
    assert order.items.get().piece.sale_state == "sold"


def test_payload_limits(client: APIClient) -> None:
    assert client.post(URL, b"x" * 65537, content_type="application/json").status_code == 413
    assert client.post(URL, b"not JSON", content_type="application/json").status_code == 400


def test_sync(order: Order, client: APIClient) -> None:
    url = f"/api/v1/orders/{order.public_token}/payment-sync"
    with patch(
        "apps.payments.api.WompiClient.get_transaction",
        return_value=replace(tx_for(order), reference="foreign"),
    ):
        assert (
            client.post(url, {"transaction_id": "foreign"}, format="json").data["code"]
            == "transaction_not_found"
        )
    with patch("apps.payments.api.WompiClient.get_transaction", return_value=tx_for(order)):
        response = client.post(url, {"transaction_id": "tx-123"}, format="json")
    assert response.status_code == 200 and response.data["payment_status"] == "approved"
    assert PaymentEvent.objects.get().source == "sync"


@pytest.mark.parametrize("known", [False, True])
def test_reconcile(order: Order, known: bool) -> None:
    attempt = order.payment_attempts.get()
    PaymentAttempt.objects.filter(pk=attempt.pk).update(
        created_at=timezone.now() - timedelta(minutes=11),
        provider_transaction_id="tx-123" if known else None,
    )
    method = "get_transaction" if known else "find_by_reference"
    with patch(f"apps.payments.tasks.WompiClient.{method}", return_value=None):
        assert reconcile_pending() == 0
    with patch(f"apps.payments.tasks.WompiClient.{method}", return_value=tx_for(order)) as lookup:
        assert reconcile_pending() == 1
    lookup.assert_called_once_with("tx-123" if known else attempt.reference)
    order.refresh_from_db()
    assert order.payment_status == "approved"


@override_settings(WOMPI_PRIVATE_KEY="prv_test_private")
def test_client_errors() -> None:
    with patch("apps.payments.wompi.urlopen", side_effect=OSError("secret")):
        assert WompiClient().get_transaction("tx") is None
        assert WompiClient().find_by_reference("ref") is None


@pytest.fixture
def operator() -> User:
    user = User.objects.create_user(
        username="operator", email="operator@example.com", password="test-password"
    )
    user.user_permissions.add(Permission.objects.get(codename="confirm_manual_payment"))
    return user


def proof(data: bytes = b"%PDF-1.7\nproof") -> SimpleUploadedFile:
    return SimpleUploadedFile("proof.pdf", data)


def manual_order(order: Order) -> Order:
    order.payment_channel = "manual"
    order.payment_status = "awaiting_manual_payment"
    order.save()
    return order


@pytest.mark.parametrize("expired,taken", [(False, False), (True, False), (True, True)])
def test_manual(
    order: Order,
    operator: User,
    tmp_path: Any,
    expired: bool,
    taken: bool,
    django_capture_on_commit_callbacks: Any,
) -> None:
    manual_order(order)
    if expired:
        release_reservation(order.reservations.get().pk, reason="reservation_expired")
        expire_stale_orders()
    if taken:
        Piece.objects.filter(pk=order.items.get().piece_id).update(sale_state="sold")
    request = RequestFactory().post("/")
    request.user = operator
    with (
        override_settings(PRIVATE_MEDIA_ROOT=tmp_path),
        patch("apps.orders.events.order_paid") as hook,
        django_capture_on_commit_callbacks(execute=True),
    ):
        if taken:
            with pytest.raises(CheckoutError):
                confirm_manual_payment(
                    order, actor=operator, reference="transfer", proof=proof(), request=request
                )
            assert not list(tmp_path.iterdir())
            return
        attempt = confirm_manual_payment(
            order, actor=operator, reference="transfer", proof=proof(), request=request
        )
        assert attempt.manual_proof.name is not None
        assert attempt.manual_proof.storage.exists(attempt.manual_proof.name)
        assert str(tmp_path) in attempt.manual_proof.path
        with pytest.raises(ValueError):
            _ = attempt.manual_proof.url
    hook.assert_called_once_with(order.pk)
    assert AuditLog.objects.filter(action="payments.approved", actor=operator).exists()
    order.refresh_from_db()
    assert order.payment_status == "approved"


@pytest.mark.parametrize(
    "data", [b"<svg><script/></svg>", b"fake PDF", b"%PDF", b"x" * (10 * 1024 * 1024 + 1)]
)
def test_manual_invalid_proof(order: Order, operator: User, data: bytes) -> None:
    manual_order(order)
    request = RequestFactory().post("/")
    request.user = operator
    with pytest.raises(ValidationError):
        confirm_manual_payment(
            order, actor=operator, reference="ref", proof=proof(data), request=request
        )
    assert not order.payment_attempts.filter(channel="manual").exists()


def test_manual_permission(order: Order) -> None:
    user = User.objects.create_user(username="content", email="content@example.com")
    with pytest.raises(PermissionDenied):
        confirm_manual_payment(
            manual_order(order),
            actor=user,
            reference="ref",
            proof=proof(),
            request=RequestFactory().post("/"),
        )


def test_manual_image_and_download(order: Order, operator: User, tmp_path: Any) -> None:
    manual_order(order)
    request = RequestFactory().post("/")
    request.user = operator
    image = BytesIO()
    Image.new("RGB", (10, 10)).save(image, format="PNG")
    with override_settings(PRIVATE_MEDIA_ROOT=tmp_path):
        attempt = confirm_manual_payment(
            order, actor=operator, reference="ref", proof=proof(image.getvalue()), request=request
        )
        assert attempt.manual_proof.name is not None
        assert attempt.manual_proof.name.endswith(".webp")
        model_admin = cast(PaymentAttemptAdmin, site._registry[PaymentAttempt])
        with pytest.raises(PermissionDenied):
            model_admin.download(request, attempt.pk)
        operator.user_permissions.add(Permission.objects.get(codename="view_paymentattempt"))
        request.user = User.objects.get(pk=operator.pk)
        response = model_admin.download(request, attempt.pk)
        assert (
            response["X-Content-Type-Options"] == "nosniff"
            and "attachment" in response["Content-Disposition"]
        )
        response.close()


def test_one_approved_constraint(order: Order) -> None:
    attempt = order.payment_attempts.get()
    apply_transaction(tx_for(order), source="webhook")
    with pytest.raises(IntegrityError), transaction.atomic():
        PaymentAttempt.objects.create(
            order=order,
            channel="wompi",
            sequence=2,
            reference="second",
            amount_cents=attempt.amount_cents,
            status="APPROVED",
        )


@override_settings(DEBUG=False)
def test_simulator_disabled() -> None:
    with pytest.raises(CommandError, match="DEBUG"):
        call_command("simulate_wompi_event", reference="missing", status="APPROVED")


@override_settings(DEBUG=True, WOMPI_ALLOW_FAKE_API=True, WOMPI_API_URL="http://wompi-fake:8080/v1")
def test_simulator(order: Order) -> None:
    import json
    from unittest.mock import MagicMock

    response = MagicMock()
    response.read.return_value = b'{"webhook_status": 200}'
    response.__enter__.return_value = response
    with patch(
        "apps.payments.management.commands.simulate_wompi_event.urlopen", return_value=response
    ) as transport:
        call_command(
            "simulate_wompi_event",
            reference=order.payment_attempts.get().reference,
            status="APPROVED",
        )
    request = transport.call_args.args[0]
    assert request.full_url == "http://wompi-fake:8080/control"
    assert json.loads(request.data)["transaction"]["status"] == "APPROVED"
    assert json.loads(request.data)["emit"] is True


def test_pending_method_and_stale_status(order: Order) -> None:
    tx = tx_for(order, "PENDING", payment_method_type="PSE")
    assert apply_transaction(tx, source="webhook") == "applied"
    attempt = order.payment_attempts.get()
    assert attempt.payment_method_type == "PSE" and attempt.provider_transaction_id == tx.id
    apply_transaction(replace(tx, status="APPROVED"), source="webhook")
    assert apply_transaction(replace(tx, status="DECLINED"), source="webhook") == "ignored_event"
    order.refresh_from_db()
    assert order.payment_status == "approved"
    assert AuditLog.objects.filter(action="payments.approved").count() == 1


@override_settings(WOMPI_PUBLIC_KEY="pub_test_x", WOMPI_INTEGRITY_SECRET="test_integrity_secret")
def test_expired_checkout_and_retry(order: Order, client: APIClient) -> None:
    apply_transaction(tx_for(order, "DECLINED"), source="webhook")
    url = f"/api/v1/orders/{order.public_token}"
    assert client.get(url).data["payment"]["can_retry"]
    Order.objects.filter(pk=order.pk).update(
        reservation_expires_at=timezone.now() - timedelta(seconds=1)
    )
    data = client.get(url).data
    assert data["wompi"] is None and not data["payment"]["can_retry"]
    assert (
        client.post(
            url + "/payment-attempts", {}, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid4())
        ).data["code"]
        == "payment_not_retryable"
    )


@pytest.mark.parametrize(
    "role,allowed", [("Propietario", True), ("Operaciones", True), ("Contenido", False)]
)
def test_role_permissions(role: str, allowed: bool) -> None:
    from django.contrib.auth.models import Group

    user = User.objects.create_user(username="role", email="role@example.com")
    user.groups.add(Group.objects.get(name=role))
    for permission in (
        "payments.confirm_manual_payment",
        "payments.view_paymentattempt",
        "payments.view_paymentevent",
    ):
        assert user.has_perm(permission) is allowed


@pytest.mark.parametrize("status", ["declined", "error"])
def test_old_order_state_approval(order: Order, status: str) -> None:
    # Legacy order states remain compatible with money received from the provider.
    Order.objects.filter(pk=order.pk).update(payment_status=status)
    assert apply_transaction(tx_for(order), source="webhook") == "applied"


@override_settings(WOMPI_PRIVATE_KEY="prv_test_private")
def test_client_request_contract(order: Order) -> None:
    from dataclasses import asdict
    from unittest.mock import MagicMock

    tx = tx_for(order)
    response = MagicMock()
    response.__enter__.return_value = response
    response.status = 200
    import json

    response.read.return_value = json.dumps({"data": asdict(tx)}).encode()
    with patch("apps.payments.wompi.urlopen", return_value=response) as get:
        assert WompiClient().get_transaction("id/unsafe") == tx
    request = get.call_args.args[0]
    assert request.full_url.endswith("/transactions/id%2Funsafe")
    assert request.get_header("Authorization") == "Bearer prv_test_private"
    assert get.call_args.kwargs["timeout"] == 8
    response.read.return_value = json.dumps(
        {"data": [asdict(replace(tx, reference="foreign")), asdict(tx)]}
    ).encode()
    with patch("apps.payments.wompi.urlopen", return_value=response):
        assert WompiClient().find_by_reference(tx.reference) == tx
        response.status = 503
        assert WompiClient().get_transaction(tx.id) is None
        response.status = 200
        response.read.return_value = b"not json"
        assert WompiClient().get_transaction(tx.id) is None


@override_settings(WOMPI_EVENTS_SECRET="secret")
def test_webhook_no_csrf_and_no_session(order: Order) -> None:
    client = APIClient(enforce_csrf_checks=True)
    client.cookies["sessionid"] = "untrusted"
    with patch("apps.payments.wompi.WompiClient.get_transaction", return_value=tx_for(order)):
        assert client.post(URL, event(tx_for(order)), format="json").status_code == 200


def test_event_is_append_only(order: Order) -> None:
    apply_transaction(tx_for(order), source="sync")
    event_record = PaymentEvent.objects.get()
    with pytest.raises(ValueError):
        event_record.save()
    with pytest.raises(ValueError):
        PaymentEvent.objects.all().update(outcome="mismatch")
    with pytest.raises(ValueError):
        event_record.delete()
