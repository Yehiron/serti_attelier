from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from apps.orders.api import ERRORS, BrowserThrottle, BrowserView
from apps.orders.exceptions import CheckoutError
from apps.orders.models import Order
from apps.orders.response_serializers import OrderDetailSerializer, WompiCheckoutSerializer
from apps.orders.selectors import order_detail

from .services import apply_transaction, checkout_data, create_wompi_attempt, record_event
from .wompi import WompiClient, WompiTransaction, verify_event


def get_order(token: str) -> Order:
    order = Order.objects.filter(public_token=token).first()
    if order is None:
        raise CheckoutError("order_not_found", status=404)
    return order


class SyncThrottle(BrowserThrottle):
    scope = "payment_sync"


class AttemptsThrottle(BrowserThrottle):
    scope = "payment_attempts"


class AttemptResponseSerializer(serializers.Serializer[Any]):
    wompi = WompiCheckoutSerializer(allow_null=True)


class SyncInputSerializer(serializers.Serializer[Any]):
    transaction_id = serializers.CharField(max_length=200)


class PaymentAttemptsView(BrowserView):
    throttle_classes = [AttemptsThrottle]

    @extend_schema(
        request=None,
        parameters=[
            OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)
        ],
        responses={201: AttemptResponseSerializer, **ERRORS},
    )
    def post(self, request: Request, public_token: str) -> Response:
        try:
            key = UUID(request.headers.get("Idempotency-Key", ""))
        except ValueError as exc:
            raise CheckoutError("validation_error") from exc
        order = get_order(public_token)
        create_wompi_attempt(order, key=key, retry=True)
        return Response({"wompi": checkout_data(order)}, status=201)


class PaymentSyncView(BrowserView):
    throttle_classes = [SyncThrottle]

    @extend_schema(request=SyncInputSerializer, responses={200: OrderDetailSerializer, **ERRORS})
    def post(self, request: Request, public_token: str) -> Response:
        order = get_order(public_token)
        transaction_id = (
            request.data.get("transaction_id") if isinstance(request.data, dict) else None
        )
        if not isinstance(transaction_id, str) or not transaction_id or len(transaction_id) > 200:
            raise CheckoutError("transaction_not_found", status=404)
        tx = WompiClient().get_transaction(transaction_id)
        if (
            tx is None
            or not order.payment_attempts.filter(reference=tx.reference, channel="wompi").exists()
        ):
            raise CheckoutError("transaction_not_found", status=404)
        apply_transaction(tx, source="sync")
        return Response(order_detail(public_token))


@csrf_exempt
def wompi_events(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return JsonResponse({}, status=405)
    # Bound the stream before JSON decoding, including requests without Content-Length.
    raw = request.read(65537)
    if len(raw) > 65536:
        return JsonResponse({}, status=413)
    try:
        body: Any = json.loads(raw)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return JsonResponse({}, status=400)
    if not isinstance(body, dict):
        record_event(None, outcome="rejected_checksum", source="webhook", checksum_valid=False)
        return JsonResponse({})
    data = body.get("data")
    tx = WompiTransaction.parse(data.get("transaction")) if isinstance(data, dict) else None
    valid = verify_event(body)
    event = body.get("event")
    if not valid:
        record_event(tx, outcome="rejected_checksum", source="webhook", checksum_valid=False)
    elif event != "transaction.updated" or tx is None:
        record_event(
            tx,
            outcome="ignored_event",
            source="webhook",
            checksum_valid=True,
            provider_event=event if isinstance(event, str) else "",
        )
    else:
        apply_transaction(tx, source="webhook")
    return JsonResponse({})
