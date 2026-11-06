from dataclasses import replace
from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest
from django.db import DatabaseError
from django.test import RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.orders.exceptions import CheckoutError
from apps.orders.services import compute_quote
from apps.payments.models import PaymentAttempt, PaymentEvent
from apps.payments.services import apply_transaction, confirm_manual_payment, create_wompi_attempt
from apps.payments.tasks import reconcile_pending, verify_wompi_event

from .test_payments import URL, event, operator, proof, tx_for  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("field,value", [("reference", "manipulada"), ("amount_in_cents", 1)])
def test_manipulated_event(order: Any, client: Any, field: Any, value: Any) -> None:
    canonical = tx_for(order)
    body = event(replace(canonical, **{field: value}))
    with patch("apps.payments.wompi.WompiClient.get_transaction", return_value=canonical):
        assert client.post(URL, body, format="json").status_code == 200
    order.refresh_from_db()
    assert order.payment_status == "pending" and not order.needs_attention
    assert order.items.get().piece.sale_state != "sold"
    assert PaymentEvent.objects.filter(outcome="mismatch").exists()


@pytest.mark.parametrize("status", ["DECLINED", "VOIDED"])
def test_canonical_status_wins(order: Any, client: Any, status: Any) -> None:
    canonical = replace(tx_for(order), status=status)
    with patch("apps.payments.wompi.WompiClient.get_transaction", return_value=canonical):
        assert client.post(URL, event(tx_for(order)), format="json").status_code == 200
    order.refresh_from_db()
    assert order.payment_status == "pending"
    assert order.payment_attempts.get().status == status
    assert client.get(f"/api/v1/orders/{order.public_token}").data["payment"]["can_retry"]
    assert create_wompi_attempt(order, retry=True).sequence == 2


@pytest.mark.parametrize("field,value", [("currency", "USD"), ("amount_in_cents", 1)])
def test_canonical_mismatch_attention(order: Any, client: Any, field: Any, value: Any) -> None:
    canonical = replace(tx_for(order), **{field: value})
    with patch("apps.payments.wompi.WompiClient.get_transaction", return_value=canonical):
        assert client.post(URL, event(canonical), format="json").status_code == 200
    order.refresh_from_db()
    assert order.needs_attention and order.payment_status == "pending"
    assert order.items.get().piece.sale_state != "sold"


def test_unavailable_queues_persisted_receipt_then_recovers(order: Any, client: Any) -> None:
    tx = tx_for(order)
    with (
        patch("apps.payments.wompi.WompiClient.get_transaction", return_value=None),
        patch("apps.payments.tasks.verify_wompi_event.delay") as queue,
    ):
        assert client.post(URL, event(tx), format="json").status_code == 200
    receipt = PaymentEvent.objects.get()
    queue.assert_called_once_with(receipt.pk)
    order.refresh_from_db()
    assert order.payment_status == "pending"
    with patch("apps.payments.wompi.WompiClient.get_transaction", return_value=tx):
        verify_wompi_event.run(receipt.pk)
    order.refresh_from_db()
    assert order.payment_status == "approved"


def test_persist_or_enqueue_failure_is_retryable(order: Any, client: Any) -> None:
    with patch("apps.payments.api.record_event", side_effect=DatabaseError):
        assert client.post(URL, event(tx_for(order)), format="json").status_code == 503
    with (
        patch("apps.payments.wompi.WompiClient.get_transaction", return_value=None),
        patch("apps.payments.tasks.verify_wompi_event.delay", side_effect=OSError),
    ):
        assert client.post(URL, event(tx_for(order)), format="json").status_code == 503
    order.refresh_from_db()
    assert order.payment_status == "pending"


def test_retry_delay(order: Any, client: Any) -> None:
    with (
        patch("apps.payments.wompi.WompiClient.get_transaction", return_value=None),
        patch("apps.payments.tasks.verify_wompi_event.delay"),
    ):
        client.post(URL, event(tx_for(order)), format="json")
        with (
            patch.object(verify_wompi_event, "retry", side_effect=RuntimeError) as retry,
            pytest.raises(RuntimeError),
        ):
            verify_wompi_event.run(PaymentEvent.objects.get().pk)
        retry.assert_called_once_with(countdown=60)


@pytest.mark.parametrize(
    "days,known,consulted", [(3, False, True), (8, False, False), (8, True, True)]
)
def test_reconcile_old_pending(order: Any, days: Any, known: Any, consulted: Any) -> None:
    PaymentAttempt.objects.filter(order=order).update(
        created_at=timezone.now() - timedelta(days=days),
        provider_transaction_id="tx-123" if known else None,
    )
    method = "get_transaction" if known else "find_by_reference"
    with patch(f"apps.payments.tasks.WompiClient.{method}", return_value=None) as lookup:
        reconcile_pending()
    assert lookup.called is consulted


def test_reconcile_approved_voided(order: Any) -> None:
    tx = tx_for(order)
    apply_transaction(tx, source="sync")
    with patch(
        "apps.payments.tasks.WompiClient.get_transaction", return_value=replace(tx, status="VOIDED")
    ):
        assert reconcile_pending() == 1
    order.refresh_from_db()
    assert order.payment_status == "voided" and order.needs_attention
    assert order.payment_attempts.get().last_reconciled_at is not None


@override_settings(WOMPI_RECONCILE_BATCH=1)
def test_reconcile_batch_and_fairness(order: Any) -> None:
    first = order.payment_attempts.get()
    PaymentAttempt.objects.filter(pk=first.pk).update(created_at=timezone.now() - timedelta(days=1))
    second = PaymentAttempt.objects.create(
        order=order,
        channel="wompi",
        sequence=2,
        reference="second",
        amount_cents=first.amount_cents,
        currency="COP",
    )
    PaymentAttempt.objects.filter(pk=second.pk).update(
        created_at=timezone.now() - timedelta(days=1)
    )
    with patch("apps.payments.tasks.WompiClient.find_by_reference", return_value=None) as lookup:
        reconcile_pending()
        reconcile_pending()
    assert [call.args[0] for call in lookup.call_args_list] == [first.reference, second.reference]


def test_repeated_failures_only_log(order: Any, caplog: Any) -> None:
    PaymentAttempt.objects.filter(order=order).update(
        created_at=timezone.now() - timedelta(days=1),
        reconcile_failures=4,
    )
    with patch("apps.payments.tasks.WompiClient.find_by_reference", return_value=None):
        reconcile_pending()
    assert "fallos de conciliación repetidos" in caplog.text
    order.refresh_from_db()
    assert not order.needs_attention


@override_settings(WOMPI_PRIVATE_KEY="")
def test_disabled_channel_and_creation(order: Any) -> None:
    quote, _ = compute_quote([], "", wants_certificate=False)
    assert quote.payment_channels == ("manual",)
    with pytest.raises(CheckoutError) as exc:
        create_wompi_attempt(order, retry=True)
    assert "Wompi no está disponible" in str(exc.value.extra)


def test_manual_wompi_rejected_service_and_admin(order: Any, operator: Any, client: Any) -> None:  # noqa: F811
    with pytest.raises(CheckoutError):
        confirm_manual_payment(
            order,
            actor=operator,
            reference="ref",
            proof=proof(),
            request=RequestFactory().post("/"),
        )
    operator.is_staff = True
    operator.is_superuser = True
    operator.save()
    client.force_login(operator, backend="django.contrib.auth.backends.ModelBackend")
    with override_settings(ADMIN_2FA_REQUIRED=False):
        response = client.post(
            reverse("admin:orders-confirm-manual", args=[order.pk]),
            {"reference": "ref", "proof": proof()},
        )
    assert response.status_code == 200
    assert response.context_data["form"].errors
    order.refresh_from_db()
    assert order.payment_status == "pending"
    assert not order.payment_attempts.filter(channel="manual").exists()


@pytest.mark.parametrize("source", ["sync", "reconciliation"])
@pytest.mark.parametrize("field,value", [("currency", "USD"), ("amount_in_cents", 1)])
def test_all_canonical_sources_validate_attempt(
    order: Any, client: Any, source: str, field: str, value: Any
) -> None:
    tx = replace(tx_for(order), **{field: value})
    with patch("apps.payments.wompi.WompiClient.get_transaction", return_value=tx):
        if source == "sync":
            response = client.post(
                f"/api/v1/orders/{order.public_token}/payment-sync",
                {"transaction_id": tx.id},
                format="json",
            )
            assert response.status_code == 200
        else:
            PaymentAttempt.objects.filter(order=order).update(
                created_at=timezone.now() - timedelta(days=3),
                provider_transaction_id=tx.id,
            )
            reconcile_pending()
    order.refresh_from_db()
    assert order.needs_attention and order.payment_status == "pending"
    assert order.items.get().piece.sale_state != "sold"


@pytest.mark.parametrize("field,value", [("id", "foreign"), ("reference", "foreign")])
def test_reconciliation_rejects_foreign_response(order: Any, field: str, value: Any) -> None:
    tx = replace(tx_for(order), **{field: value})
    PaymentAttempt.objects.filter(order=order).update(
        created_at=timezone.now() - timedelta(days=3),
        provider_transaction_id="tx-123",
    )
    with patch("apps.payments.wompi.WompiClient.get_transaction", return_value=tx):
        reconcile_pending()
    order.refresh_from_db()
    assert order.payment_status == "pending" and not order.needs_attention
    assert PaymentEvent.objects.get().outcome == "mismatch"
