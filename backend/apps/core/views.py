from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from . import health

_status_schema = inline_serializer(
    name="HealthStatus",
    fields={
        "status": serializers.ChoiceField(choices=["ok", "unavailable"]),
        "checks": serializers.DictField(child=serializers.BooleanField(), required=False),
    },
)


class LiveView(APIView):
    """The process is up. Never touches dependencies."""

    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(responses={200: _status_schema})
    def get(self, request: Request) -> Response:
        return Response({"status": "ok"})


class ReadyView(APIView):
    """The process can serve traffic: database and Redis respond."""

    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(responses={200: _status_schema, 503: _status_schema})
    def get(self, request: Request) -> Response:
        checks = {"database": health.check_database(), "redis": health.check_redis()}
        ready = all(checks.values())
        return Response(
            {"status": "ok" if ready else "unavailable", "checks": checks},
            status=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        )
