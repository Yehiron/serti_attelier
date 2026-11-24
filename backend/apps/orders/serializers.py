import re
from typing import Any

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


class ContactSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=200)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=40)

    def validate_phone(self, value: str) -> str:
        phone = re.sub(r"[\s()\-]", "", value)
        if re.fullmatch(r"3[0-9]{9}", phone):
            phone = "+57" + phone
        if not re.fullmatch(r"\+[1-9][0-9]{1,14}", phone):
            raise serializers.ValidationError(_("Usa un teléfono E.164 válido."))
        return phone


class ShippingSerializer(serializers.Serializer[Any]):
    municipality_code = serializers.RegexField(r"^[0-9]{5}$")
    address_line = serializers.CharField(max_length=300)
    address_extra = serializers.CharField(
        max_length=300, required=False, default="", allow_blank=True
    )
    notes = serializers.CharField(max_length=2000, required=False, default="", allow_blank=True)


class QuoteInputSerializer(serializers.Serializer[Any]):
    email = serializers.EmailField(required=False, allow_blank=True)
    coupon_code = serializers.CharField(max_length=50, required=False, allow_blank=True)
    wants_certificate = serializers.BooleanField()


class OrderInputSerializer(QuoteInputSerializer):
    contact = ContactSerializer()
    shipping = ShippingSerializer()
    payment_channel = serializers.ChoiceField(choices=["wompi", "manual"])
    accepted_terms_version = serializers.IntegerField(required=False, allow_null=True)
    accepted_privacy_version = serializers.IntegerField(required=False, allow_null=True)
    locale = serializers.ChoiceField(choices=["es", "en"])
