from __future__ import annotations

from dataclasses import asdict
from typing import Any
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from apps.cart import services as carts
from apps.cart.selectors import cart_data, pieces
from apps.core.api.base import PublicView
from apps.core.api.serializers import ProblemSerializer
from apps.core.http import client_ip
from apps.promotions.services import email_digest

from .exceptions import CheckoutError
from .response_serializers import (
    CartSerializer,
    CreatedOrderSerializer,
    OrderDetailSerializer,
    QuoteSerializer,
)
from .selectors import created_data, order_detail
from .serializers import OrderInputSerializer, QuoteInputSerializer
from .services import compute_quote, create_order


class BrowserThrottle(SimpleRateThrottle):
    def get_cache_key(self, request: Request, view: APIView) -> str:
        return self.cache_format % {
            "scope": self.scope,
            "ident": client_ip(request._request) or "unknown",
        }


class CartThrottle(BrowserThrottle):
    scope = "cart_add"


class QuoteThrottle(BrowserThrottle):
    scope = "checkout_quote"


class OrderMinuteThrottle(BrowserThrottle):
    scope = "orders_minute"


class OrderHourThrottle(BrowserThrottle):
    scope = "orders_hour"


class BrowserView(PublicView):
    parser_classes = [JSONParser]
    throttle_classes = []


ERRORS: dict[Any, Any] = {
    (s, "application/problem+json"): ProblemSerializer for s in (404, 409, 415, 422, 429)
}


class CartView(BrowserView):
    @extend_schema(responses={200: CartSerializer, **ERRORS})
    def get(self, request: Request) -> Response:
        cart = carts.read_cart(request._request)
        removed = carts.clean_cart(cart) if cart else []
        return Response(cart_data(cart, removed))


class AddItemSerializer(serializers.Serializer[Any]):
    sku = serializers.CharField(max_length=40)


class AddItemView(BrowserView):
    throttle_classes = [CartThrottle]

    @extend_schema(request=AddItemSerializer, responses={201: CartSerializer, **ERRORS})
    def post(self, request: Request) -> Response:
        serializer = AddItemSerializer(data=request.data)
        if not serializer.is_valid():
            raise CheckoutError("validation_error", errors=serializer.errors)
        cart = carts.get_or_create_cart(request._request)
        carts.add_piece(cart, serializer.validated_data["sku"])
        response = Response(cart_data(cart), status=201)
        carts.set_cookie(response, cart)
        return response


class RemoveItemView(BrowserView):
    @extend_schema(responses={200: CartSerializer, **ERRORS})
    def delete(self, request: Request, sku: str) -> Response:
        cart = carts.read_cart(request._request)
        if cart:
            carts.remove_piece(cart, sku)
        return Response(cart_data(cart, carts.clean_cart(cart) if cart else []))


class QuoteView(BrowserView):
    throttle_classes = [QuoteThrottle]

    @extend_schema(request=QuoteInputSerializer, responses={200: QuoteSerializer, **ERRORS})
    def post(self, request: Request) -> Response:
        serializer = QuoteInputSerializer(data=request.data)
        if not serializer.is_valid():
            raise CheckoutError("validation_error", errors=serializer.errors)
        cart = carts.read_cart(request._request)
        if cart:
            carts.clean_cart(cart)
        data = serializer.validated_data
        result, _ = compute_quote(
            [p for p in pieces(cart) if p.status == "published" and p.sale_state == "available"]
            if cart
            else [],
            data.get("coupon_code", ""),
            wants_certificate=data["wants_certificate"],
            email_hash=email_digest(data["email"].strip().lower()) if data.get("email") else None,
        )
        return Response(asdict(result))


class OrdersView(BrowserView):
    throttle_classes = [OrderMinuteThrottle, OrderHourThrottle]

    @extend_schema(
        request=OrderInputSerializer,
        parameters=[
            OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)
        ],
        responses={200: CreatedOrderSerializer, 201: CreatedOrderSerializer, **ERRORS},
    )
    def post(self, request: Request) -> Response:
        try:
            key = UUID(request.headers.get("Idempotency-Key", ""))
        except ValueError as exc:
            raise CheckoutError(
                "validation_error", errors={"Idempotency-Key": [_("Usa un UUID válido.")]}
            ) from exc
        if not isinstance(request.data, dict):
            raise CheckoutError(
                "validation_error", errors={"body": [_("Se requiere un objeto JSON.")]}
            )
        order, created = create_order(
            carts.read_cart(request._request),
            request.data,
            idempotency_key=key,
            request=request._request,
        )
        return Response(created_data(order), status=201 if created else 200)


class OrderPublicThrottle(BrowserThrottle):
    scope = "order_public"


class PrivateOrderView(BrowserView):
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store, private"
        response["Referrer-Policy"] = "no-referrer"
        return response


class OrderDetailView(PrivateOrderView):
    throttle_classes = [OrderPublicThrottle]

    @extend_schema(responses={200: OrderDetailSerializer, **ERRORS})
    def get(self, request: Request, public_token: str) -> Response:
        return Response(order_detail(public_token))
