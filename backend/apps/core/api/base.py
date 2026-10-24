from typing import Any

from django.conf import settings
from django.utils import translation
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView


class PublicReadThrottle(SimpleRateThrottle):
    scope = "public_reads"

    def get_rate(self) -> str:
        return str(
            getattr(
                settings, "PUBLIC_READ_RATE", api_settings.DEFAULT_THROTTLE_RATES["public_reads"]
            )
        )

    def get_cache_key(self, request: Request, view: APIView) -> str:
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class PublicView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []
    throttle_classes = [PublicReadThrottle]
    locale = "es"
    previous_language: str | None = None

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        self.previous_language = translation.get_language()
        locale = request.query_params.get("locale")
        if locale not in ("es", "en"):
            locale = translation.get_language_from_request(request)
        self.locale = locale if locale in ("es", "en") else "es"
        translation.activate(self.locale)
        super().initial(request, *args, **kwargs)

    def finalize_response(
        self, request: Request, response: Response, *args: Any, **kwargs: Any
    ) -> Response:
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Content-Language"] = self.locale
        translation.activate(self.previous_language or "es")
        return response
