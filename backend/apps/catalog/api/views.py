from typing import Any

from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.api.base import PublicView
from apps.core.api.serializers import public_responses
from apps.core.models import SiteSettings
from apps.core.selectors import get_solo

from .. import selectors
from ..models import Category, Collection, Material, Piece, Stone
from .serializers import (
    CatalogFiltersSerializer,
    CatalogListSerializer,
    ImageSerializer,
    PieceDetailSerializer,
    PieceListSerializer,
    TaxonomySerializer,
)


class CatalogPagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = "page_size"
    max_page_size = 48


class CatalogExistsView(PublicView):
    @extend_schema(
        parameters=[
            OpenApiParameter(
                "kind", required=True, enum=["piece", "category", "collection", "stone", "material"]
            ),
            OpenApiParameter("slug", required=True),
            OpenApiParameter("locale", enum=["es", "en"]),
        ],
        responses={204: None, 404: None},
    )
    def get(self, request: Request) -> Response:
        kind = request.query_params.get("kind")
        slug = request.query_params.get("slug", "")
        models = {
            "piece": Piece,
            "category": Category,
            "collection": Collection,
            "stone": Stone,
            "material": Material,
        }
        if kind not in models or not slug:
            raise serializers.ValidationError("Se requieren kind y slug válidos.")
        qs: Any = models[kind]._default_manager.filter(selectors.localized_slug(self.locale, slug))
        if kind == "piece":
            qs = qs.filter(status=Piece.Status.PUBLISHED)
        elif kind == "category":
            from django.db.models import Q

            qs = qs.filter(is_active=True).filter(
                Q(parent__isnull=True) | Q(parent__is_active=True)
            )
        elif kind == "collection":
            qs = qs.filter(is_active=True)
        response = Response(status=204 if qs.exists() else 404)
        response["Cache-Control"] = "public, max-age=60"
        return response


class TaxonomyView(PublicView):
    @extend_schema(
        responses=public_responses(TaxonomySerializer),
        parameters=[OpenApiParameter("locale", enum=["es", "en"])],
    )
    def get(self, request: Request) -> Response:
        return Response(
            TaxonomySerializer(
                {
                    "categories": Category.objects.filter(is_active=True, parent=None)
                    .exclude(slug_es__isnull=True)
                    .exclude(slug_es="")
                    .prefetch_related("children"),
                    "collections": (
                        Collection.objects.filter(is_active=True)
                        .exclude(slug_es__isnull=True)
                        .exclude(slug_es="")
                    ),
                    "stones": Stone.objects.exclude(slug_es__isnull=True).exclude(slug_es=""),
                    "materials": Material.objects.exclude(slug_es__isnull=True).exclude(slug_es=""),
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
        search_ids = selectors.search_piece_ids(params["q"]) if params.get("q") else None
        paginator = CatalogPagination()
        page = paginator.paginate_queryset(
            selectors.filter_pieces(params, self.locale, search_ids=search_ids), request, view=self
        )
        response = paginator.get_paginated_response(PieceListSerializer(page, many=True).data)
        response.data["facets"] = selectors.piece_facets(params, self.locale, search_ids=search_ids)
        return response


class PieceDetailView(PublicView):
    @extend_schema(
        responses=public_responses(PieceDetailSerializer, not_found=True),
        parameters=[OpenApiParameter("locale", enum=["es", "en"])],
    )
    def get(self, request: Request, slug: str) -> Response:
        return Response(
            PieceDetailSerializer(
                selectors.piece_detail(slug, self.locale),
                context={
                    "locale": self.locale,
                    "settings": SiteSettings.objects.filter(pk=1).first() or get_solo(),
                },
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


class WishlistStatusView(PublicView):
    def get(self, request: Request) -> Response:
        skus = [
            sku.strip() for sku in request.query_params.get("skus", "").split(",") if sku.strip()
        ]
        if len(skus) > 50:
            raise serializers.ValidationError(_("Se permiten hasta 50 SKU."))
        pieces = Piece.objects.filter(status=Piece.Status.PUBLISHED, sku__in=skus).prefetch_related(
            "images"
        )
        result: dict[str, Any] = {sku: {"state": "missing"} for sku in skus}
        for piece in pieces:
            image = next(
                (
                    item
                    for item in piece.images.all()
                    if item.is_primary and item.processing_status == "ready"
                ),
                None,
            )
            result[piece.sku] = {
                "state": piece.sale_state,
                "slugs": {"es": piece.slug_es, "en": piece.slug_en or piece.slug_es},
                "name": getattr(piece, f"name_{self.locale}") or piece.name_es,
                "price": piece.effective_price.as_dict(),
                "image": dict(ImageSerializer(image).data) if image else None,
            }
        return Response(result)
