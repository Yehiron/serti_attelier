from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_serializer
from rest_framework import serializers
from rest_framework.response import Response

from apps.orders.api import ERRORS, BrowserThrottle, BrowserView
from apps.orders.exceptions import CheckoutError
from apps.orders.selectors import legal_versions

from .models import ContactInquiry, normalize_phone
from .tasks import notify_atelier, send_acknowledgement


class MinuteThrottle(BrowserThrottle):
    scope = "contact_minute"


class HourThrottle(BrowserThrottle):
    scope = "contact_hour"


if TYPE_CHECKING:
    _ContactSerializerBase = serializers.ModelSerializer[ContactInquiry]
else:
    _ContactSerializerBase = serializers.ModelSerializer


# Distinct schema name: orders already exposes a "Contact" component.
@extend_schema_serializer(component_name="ContactMessage")
class ContactSerializer(_ContactSerializerBase):
    accepted_privacy_version = serializers.IntegerField(required=False, allow_null=True)
    website = serializers.CharField(required=False, allow_blank=True, max_length=2048)
    elapsed_ms = serializers.IntegerField(min_value=0)
    message = serializers.CharField(min_length=20, max_length=2000)

    def validate_phone(self, value):
        try:
            return normalize_phone(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc

    class Meta:
        model = ContactInquiry
        fields = (
            "name",
            "email",
            "phone",
            "topic",
            "piece_sku",
            "message",
            "preferred_channel",
            "accepted_privacy_version",
            "locale",
            "website",
            "elapsed_ms",
        )


class ContactView(BrowserView):
    throttle_classes = [MinuteThrottle, HourThrottle]

    @extend_schema(request=ContactSerializer, responses={201: None, **ERRORS})
    def post(self, request):
        # Las trampas responden igual para no informar al emisor automatizado.
        if isinstance(request.data, dict) and request.data.get("website"):
            return Response({"received": True}, status=201)
        serializer = ContactSerializer(data=request.data)
        if not serializer.is_valid():
            raise CheckoutError("validation_error", errors=serializer.errors)
        data = dict(serializer.validated_data)
        if data["elapsed_ms"] < 3000:
            return Response({"received": True}, status=201)
        version = data.pop("accepted_privacy_version", None)
        current = legal_versions()["privacy"]
        if current is None or version != current:
            raise CheckoutError("consent_required")
        data.pop("website", None)
        data.pop("elapsed_ms")
        with transaction.atomic():
            inquiry = ContactInquiry.objects.create(privacy_version=version, **data)
            transaction.on_commit(
                lambda: (notify_atelier.delay(inquiry.pk), send_acknowledgement.delay(inquiry.pk))
            )
        return Response({"received": True}, status=201)
