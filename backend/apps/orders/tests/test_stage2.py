# ruff: noqa: F811
from dataclasses import replace
from importlib import import_module
from unittest.mock import patch

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import RequestFactory
from django.urls import reverse

from apps.accounts.roles import OPERACIONES, PROPIETARIO
from apps.audit.models import AuditLog
from apps.core.tests.test_dashboard_client import staff
from apps.notifications.models import NotificationDelivery
from apps.notifications.services import enqueue, retry_due
from apps.orders.exceptions import CheckoutError
from apps.orders.incidents import open_incident, open_manual_incident, resolve_incident
from apps.orders.models import Order, OrderIncident
from apps.orders.services import cancel_order, expire_stale_orders, transition_status
from apps.payments.services import apply_transaction, confirm_manual_payment, create_wompi_attempt
from apps.payments.tests.conftest import order  # noqa: F401
from apps.payments.tests.test_payments import tx_for

pytestmark = pytest.mark.django_db


def request_for(user, data=None):
    request = RequestFactory().post("/", data or {})
    request.user = user
    return request


def test_durable_before_commit_and_duplicate(order):
    with patch("apps.notifications.services.dispatch") as dispatch, transaction.atomic():
        apply_transaction(tx_for(order), source="webhook")
        assert order.deliveries.filter(event="order_paid", status="queued", attempts=0).count() == 3
        dispatch.assert_not_called()
        assert apply_transaction(tx_for(order), source="webhook") == "duplicate"
        assert order.deliveries.count() == 3


def test_broker_failure_recovered(order, django_capture_on_commit_callbacks):
    with (
        patch("apps.notifications.tasks.send_delivery.delay", side_effect=OSError("secret")),
        django_capture_on_commit_callbacks(execute=True),
    ):
        enqueue(order, "order_paid")
    assert order.deliveries.filter(status="queued", attempts=0).count() == 3
    with patch("apps.notifications.services.dispatch") as dispatch:
        assert retry_due() == 3
        assert dispatch.call_count == 3


def test_template_failure_keeps_money_and_incident(order, caplog):
    with patch(
        "django.template.loader.get_template", side_effect=RuntimeError("secret@email.test")
    ):
        assert apply_transaction(tx_for(order), source="webhook") == "applied"
    order.refresh_from_db()
    assert order.payment_status == "approved" and order.payment_attempts.get().status == "APPROVED"
    assert order.needs_attention and order.incidents.filter(kind="other", status="open").exists()
    assert not order.deliveries.exists()
    assert "secret@email.test" not in caplog.text


def cancel(order, actor, **kwargs):
    cancel_order(
        order,
        actor=actor,
        reason=kwargs.pop("reason", "Cliente desiste"),
        notify=False,
        expected_status=kwargs.pop("expected_status", "unfulfilled"),
        **kwargs,
    )


def test_cancel_permissions_reason_releases_and_rejects_payments(order):
    browser, operations = staff(OPERACIONES)
    endpoint = reverse("admin:orders-card-status", args=[order.pk])
    assert (
        browser.post(
            endpoint,
            {"target": "cancelled", "note": "Cliente desiste", "expected_status": "unfulfilled"},
        ).status_code
        == 403
    )
    _, owner = staff(PROPIETARIO)
    with pytest.raises(PermissionDenied):
        cancel(order, operations)
    with pytest.raises(ValidationError, match="motivo"):
        cancel(order, owner, reason="  ")
    cancel(order, owner)
    order.refresh_from_db()
    piece = order.items.get().piece
    assert order.fulfillment_status == "cancelled"
    assert order.reservations.get().status == "released" and piece.sale_state == "available"
    assert expire_stale_orders() == 0
    assert not order.deliveries.filter(event="reservation_expired").exists()
    with pytest.raises(CheckoutError) as exc:
        create_wompi_attempt(order)
    assert "cancelado" in str(exc.value.extra)
    order.payment_channel = "manual"
    order.payment_status = "awaiting_manual_payment"
    order.save()
    with pytest.raises(CheckoutError) as exc:
        confirm_manual_payment(
            order, actor=owner, reference="bank", proof=None, request=request_for(owner)
        )
    assert "cancelado" in str(exc.value.extra)
    assert AuditLog.objects.filter(action="orders.cancelled").exists()
    assert order.deliveries.filter(event="order_cancelled", audience="serti").count() == 1
    assert not order.deliveries.filter(audience="customer").exists()


def test_paid_cancel_holds_piece_and_requires_refund(order):
    _, owner = staff(PROPIETARIO)
    apply_transaction(tx_for(order), source="webhook")
    cancel(order, owner)
    order.refresh_from_db()
    assert order.items.get().piece.sale_state == "reserved"
    assert not order.reservations.filter(status__in=["active", "converted"]).exists()
    assert order.incidents.get(kind="refund_pending").status == "open"
    assert order.needs_attention


def test_late_payment_cancelled_never_sells(order):
    _, owner = staff(PROPIETARIO)
    cancel(order, owner)
    apply_transaction(tx_for(order), source="reconciliation")
    order.refresh_from_db()
    assert order.payment_status == "approved" and order.fulfillment_status == "cancelled"
    assert order.items.get().piece.sale_state == "available"
    assert order.incidents.get(kind="cancelled_payment").status == "open"


@pytest.mark.parametrize("target,source", [("preparing", "unfulfilled"), ("shipped", "preparing")])
@pytest.mark.parametrize(
    "problem,message",
    [
        ("voided", "el pago fue anulado"),
        ("piece", "las piezas no están vendidas"),
        ("incident", "hay una incidencia abierta"),
    ],
)
def test_fulfillment_revalidates(order, target, source, problem, message):
    _, actor = staff(OPERACIONES)
    apply_transaction(tx_for(order), source="webhook")
    order.refresh_from_db()
    order.fulfillment_status = source
    order.save()
    if problem == "voided":
        apply_transaction(replace(tx_for(order), status="VOIDED"), source="webhook")
    elif problem == "piece":
        # A converted reservation belonging to another buyer cannot prove ownership.
        order.reservations.update(order=None)
    else:
        open_incident(order, OrderIncident.Kind.NO_PIECE)
    with pytest.raises(ValidationError, match=message):
        transition_status(
            order,
            "fulfillment_status",
            target,
            request=request_for(actor),
            carrier="Correo",
            expected_status=source,
        )


def test_shipping_carrier_and_voided_after_shipping(order):
    _, actor = staff(OPERACIONES)
    apply_transaction(tx_for(order), source="webhook")
    transition_status(order, "fulfillment_status", "preparing", request=request_for(actor))
    with pytest.raises(ValidationError, match="transportadora"):
        transition_status(order, "fulfillment_status", "shipped", request=request_for(actor))
    transition_status(
        order, "fulfillment_status", "shipped", request=request_for(actor), carrier="Correo"
    )
    apply_transaction(replace(tx_for(order), status="VOIDED"), source="webhook")
    order.refresh_from_db()
    assert order.fulfillment_status == "shipped" and order.payment_status == "voided"
    assert order.incidents.get(kind="voided_shipped").status == "open"


def test_incidents_permissions_dedup_sync_and_reopen(order):
    _, operations = staff(OPERACIONES)
    _, owner = staff(PROPIETARIO)
    first = open_incident(order, "no_piece")
    assert open_incident(order, "no_piece").pk == first.pk
    with pytest.raises(PermissionDenied):
        resolve_incident(first, actor=operations, note="Revisado por equipo")
    with pytest.raises(ValidationError):
        resolve_incident(first, actor=owner, note="")
    other = open_manual_incident(
        order, actor=operations, detail="Revisar el empaque", blocking=False
    )
    resolve_incident(first, actor=owner, note="Dinero devuelto")
    order.refresh_from_db()
    assert order.needs_attention
    resolve_incident(other, actor=operations, note="Empaque corregido")
    order.refresh_from_db()
    assert not order.needs_attention
    assert open_incident(order, "no_piece").pk != first.pk
    assert order.deliveries.filter(event="needs_attention").count() == 6
    assert AuditLog.objects.filter(action="orders.incident_resolved").count() == 2


def test_card_incidents_confirmation_and_permissions(order):
    browser, _ = staff(OPERACIONES)
    endpoint = reverse("admin:orders-card-incident", args=[order.pk])
    assert (
        browser.post(endpoint, {"detail": "Revisar empaque", "blocking": "on"}).status_code == 200
    )
    incident = order.incidents.get()
    assert (
        browser.post(
            endpoint, {"incident_id": incident.pk, "note": "Revisado y corregido"}
        ).status_code
        == 422
    )
    assert (
        browser.post(
            endpoint, {"incident_id": incident.pk, "note": "Revisado y corregido", "confirm": "yes"}
        ).status_code
        == 200
    )
    financial = open_incident(order, "refund_pending")
    assert (
        browser.post(
            endpoint,
            {"incident_id": financial.pk, "note": "Revisado y corregido", "confirm": "yes"},
        ).status_code
        == 403
    )


def test_bulk_partial_expected_status_no_notification(order):
    browser, _ = staff(OPERACIONES)
    apply_transaction(tx_for(order), source="webhook")
    second = Order.objects.get(pk=order.pk)
    second.pk = None
    from uuid import uuid4

    second.idempotency_key = uuid4()
    second.public_token = str(uuid4())
    second.number = "SRT-SECOND"
    second.payment_status = "voided"
    second.save()
    endpoint = reverse("admin:orders_order_changelist")
    before = NotificationDelivery.objects.count()
    response = browser.post(
        endpoint,
        {
            "action": "fulfillment",
            "_selected_action": [order.pk, second.pk],
            "apply": "1",
            "target": "preparing",
            f"expected_{order.pk}": "unfulfilled",
            f"expected_{second.pk}": "unfulfilled",
        },
        follow=True,
    )
    assert response.status_code == 200
    text = " ".join(str(m) for m in response.context["messages"])
    assert "1 pedido actualizado" in text and "SRT-SECOND" in text and "el pago fue anulado" in text
    assert NotificationDelivery.objects.count() == before
    order.refresh_from_db()
    assert order.fulfillment_status == "preparing"
    response = browser.post(
        endpoint,
        {
            "action": "fulfillment",
            "_selected_action": [order.pk],
            "apply": "1",
            "target": "shipped",
            "carrier": "Correo",
            f"expected_{order.pk}": "unfulfilled",
        },
        follow=True,
    )
    assert "El pedido cambió, recarga" in " ".join(str(m) for m in response.context["messages"])
    order.refresh_from_db()
    assert order.fulfillment_status == "preparing"


def test_migration_imports_existing_attention(order):
    # Historical state exercises the data function against migration models, twice for replay.
    Order.objects.filter(pk=order.pk).update(needs_attention=True)
    executor = MigrationExecutor(connection)
    apps = executor.loader.project_state(
        [("orders", "0006_alter_order_options_orderincident")]
    ).apps
    module = import_module("apps.orders.migrations.0006_alter_order_options_orderincident")
    editor = connection.schema_editor(atomic=False)
    module.import_existing_attention(apps, editor)
    module.import_existing_attention(apps, editor)
    incident = order.incidents.get()
    assert incident.kind == "other" and incident.status == "open" and incident.blocking
    assert incident.detail == "Incidencia previa a la actualización"
