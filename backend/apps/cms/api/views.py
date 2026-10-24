from typing import Any

from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.api.base import PublicView
from apps.core.api.serializers import ProblemSerializer

from .. import selectors
from ..models import Page
from ..preview import expires_at, verify_token
from .serializers import (
    HomeSerializer,
    PageSerializer,
    PersonalizationSerializer,
    PreviewSerializer,
    SiteSettingsSerializer,
)

PARAMETERS = [
    OpenApiParameter("locale", str, enum=["es", "en"]),
    OpenApiParameter("preview", str, description="Token de vista previa (10 minutos)."),
]


class PageNotFound(NotFound):
    default_code = "page_not_found"
    default_detail = _("No se encontró la página.")


def is_preview(request: Request) -> bool:
    if "preview" in request.query_params:
        verify_token(request.query_params["preview"])
        return True
    return False


class HomeView(PublicView):
    @extend_schema(
        parameters=PARAMETERS,
        responses={200: HomeSerializer, (403, "application/problem+json"): ProblemSerializer},
    )
    def get(self, request: Request) -> Response:
        preview = is_preview(request)
        response = Response(selectors.home(self.locale, preview))
        if preview:
            response["Cache-Control"] = "private, no-store"
        return response


class PageView(PublicView):
    @extend_schema(
        parameters=PARAMETERS,
        responses={
            200: PageSerializer,
            (403, "application/problem+json"): ProblemSerializer,
            (404, "application/problem+json"): ProblemSerializer,
        },
    )
    def get(self, request: Request, slug: str | None = None, kind: str | None = None) -> Response:
        preview = is_preview(request)
        payload: dict[str, Any] | None
        if preview:
            from apps.catalog.selectors import localized_slug

            page = (
                Page.objects.filter(kind=kind).first()
                if kind
                else Page.objects.filter(localized_slug(self.locale, slug or "")).first()
            )
            if page is None:
                raise PageNotFound()
            payload = selectors.page_payload(page, self.locale)
        else:
            payload = next(
                (
                    selectors.page_payload(page, self.locale, revision)
                    for page, revision in selectors.published_pages()
                    if (
                        page.kind == kind
                        if kind
                        else revision.snapshot[self.locale]["slug"] == slug
                    )
                ),
                None,
            )
            if payload is None:
                raise PageNotFound()
        response = Response(payload)
        if preview:
            response["Cache-Control"] = "private, no-store"
        return response


class PersonalizationView(PublicView):
    @extend_schema(parameters=[PARAMETERS[0]], responses=PersonalizationSerializer)
    def get(self, request: Request) -> Response:
        return Response(selectors.personalization(self.locale))


class SiteSettingsView(PublicView):
    @extend_schema(parameters=[PARAMETERS[0]], responses=SiteSettingsSerializer)
    def get(self, request: Request) -> Response:
        return Response(selectors.site_settings(self.locale))


class PreviewVerifyView(PublicView):
    @extend_schema(
        parameters=[OpenApiParameter("token", str, required=True)],
        responses={200: PreviewSerializer, (403, "application/problem+json"): ProblemSerializer},
    )
    def get(self, request: Request) -> Response:
        token = request.query_params.get("token", "")
        user = verify_token(token)
        response = Response({"user": user.get_username(), "expires_at": expires_at(token)})
        response["Cache-Control"] = "private, no-store"
        return response
