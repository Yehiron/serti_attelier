from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.api.base import PublicView
from apps.core.api.serializers import public_responses

from .. import selectors
from ..models import Category, Collection, Material, Piece, Stone
from .serializers import (
    CatalogFiltersSerializer,
    CatalogListSerializer,
    PieceDetailSerializer,
    PieceListSerializer,
    TaxonomySerializer,
)


class CatalogPagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = "page_size"
    max_page_size = 48


class TaxonomyView(PublicView):
    @extend_schema(
        responses=public_responses(TaxonomySerializer),
        parameters=[OpenApiParameter("locale", enum=["es", "en"])],
    )
    def get(self, request: Request) -> Response:
        return Response(
            TaxonomySerializer(
                {
                    "categories": Category.objects.filter(
                        is_active=True, parent=None
                    ).prefetch_related("children"),
                    "collections": Collection.objects.filter(is_active=True),
                    "stones": Stone.objects.all(),
                    "materials": Material.objects.all(),
                }
            ).data
        )


class PieceListView(PublicView):
    @extend_schema(
        operation_id="catalog_pieces_list",
        parameters=[CatalogFiltersSerializer],
        responses=public_responses(CatalogListSerializer, not_found=True),
    )
    def get(self, request: Request) -> Response:
        filters = CatalogFiltersSerializer(data=dict(request.query_params.items()))
        filters.is_valid(raise_exception=True)
        params = filters.validated_data
        params["stones"] = [
            slug
            for value in request.query_params.getlist("stone")
            for slug in value.split(",")
            if slug
        ]
        paginator = CatalogPagination()
        page = paginator.paginate_queryset(
            selectors.filter_pieces(params, self.locale), request, view=self
        )
        response = paginator.get_paginated_response(PieceListSerializer(page, many=True).data)
        response.data["facets"] = selectors.piece_facets(params, self.locale)
        return response


class PieceDetailView(PublicView):
    @extend_schema(
        responses=public_responses(PieceDetailSerializer, not_found=True),
        parameters=[OpenApiParameter("locale", enum=["es", "en"])],
    )
    def get(self, request: Request, slug: str) -> Response:
        return Response(
            PieceDetailSerializer(
                selectors.piece_detail(slug, self.locale), context={"locale": self.locale}
            ).data
        )


class PieceStatusView(PublicView):
    @extend_schema(
        parameters=[
            OpenApiParameter("skus", required=True, description="Hasta 50 SKU separados por comas.")
        ],
        responses=public_responses(
            {
                "type": "object",
                "additionalProperties": {
                    "type": "string",
                    "enum": ["available", "reserved", "sold", "preorder", "unavailable"],
                },
            }
        ),
    )
    def get(self, request: Request) -> Response:
        skus = [
            sku.strip() for sku in request.query_params.get("skus", "").split(",") if sku.strip()
        ]
        if len(skus) > 50:
            raise serializers.ValidationError(_("Se permiten hasta 50 SKU."))
        states = dict(
            Piece.objects.filter(status="published", sku__in=skus).values_list("sku", "sale_state")
        )
        return Response({sku: states.get(sku, "unavailable") for sku in skus})
