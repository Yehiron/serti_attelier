from typing import Any

from rest_framework import serializers

from apps.catalog.api.serializers import ImageSerializer, MoneySerializer
from apps.catalog.models import Piece


class CartItemSerializer(serializers.Serializer[Any]):
    sku = serializers.CharField()
    slug = serializers.CharField()
    name = serializers.CharField()
    image = ImageSerializer(allow_null=True)
    price = MoneySerializer()
    sale_price = MoneySerializer(allow_null=True)
    effective_price = MoneySerializer()
    sale_state = serializers.ChoiceField(choices=Piece.SaleState.choices)
    purchasable = serializers.BooleanField()


class RemovedSerializer(serializers.Serializer[Any]):
    sku = serializers.CharField()
    name = serializers.CharField()
    reason = serializers.ChoiceField(choices=["sold", "preorder", "unavailable"])


class CartSerializer(serializers.Serializer[Any]):
    items = CartItemSerializer(many=True)
    removed = RemovedSerializer(many=True)
    count = serializers.IntegerField()
    subtotal = MoneySerializer()


class QuoteLineSerializer(serializers.Serializer[Any]):
    sku = serializers.CharField()
    name = serializers.CharField()
    unit_price_cents = serializers.IntegerField()
    discount_cents = serializers.IntegerField()


class CouponResultSerializer(serializers.Serializer[Any]):
    code = serializers.CharField()
    applied = serializers.BooleanField()
    reason = serializers.CharField(allow_null=True)


class TotalsSerializer(serializers.Serializer[Any]):
    subtotal_cents = serializers.IntegerField()
    discount_cents = serializers.IntegerField()
    shipping_cents = serializers.IntegerField()
    certificate_cents = serializers.IntegerField()
    total_cents = serializers.IntegerField()
    currency = serializers.CharField()


class QuoteSerializer(TotalsSerializer):
    items = QuoteLineSerializer(many=True)
    coupon = CouponResultSerializer(allow_null=True)
    payment_channels = serializers.ListField(
        child=serializers.ChoiceField(choices=["wompi", "manual"])
    )


class CreatedOrderSerializer(serializers.Serializer[Any]):
    number = serializers.CharField()
    public_token = serializers.CharField()
    payment_channel = serializers.CharField()
    payment_status = serializers.CharField()
    total_cents = serializers.IntegerField()
    reservation_expires_at = serializers.DateTimeField(allow_null=True)
    manual_instructions = serializers.CharField(allow_null=True)


class OrderItemSerializer(QuoteLineSerializer):
    image = ImageSerializer(allow_null=True)
    piece_number = serializers.CharField(allow_null=True)


class ShippingSummarySerializer(serializers.Serializer[Any]):
    department = serializers.CharField()
    municipality = serializers.CharField()


class OrderDetailSerializer(TotalsSerializer):
    number = serializers.CharField()
    created_at = serializers.DateTimeField()
    locale = serializers.CharField()
    payment_channel = serializers.CharField()
    payment_status = serializers.CharField()
    fulfillment_status = serializers.CharField()
    items = OrderItemSerializer(many=True)
    wants_certificate = serializers.BooleanField()
    shipping = ShippingSummarySerializer()
    reservation_expires_at = serializers.DateTimeField(allow_null=True)
    manual_instructions = serializers.CharField(allow_null=True)
