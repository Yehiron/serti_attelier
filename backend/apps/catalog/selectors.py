from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

from django.contrib.postgres.search import TrigramSimilarity
from django.db import connection
from django.db.models import (
    BigIntegerField,
    Case,
    Count,
    Exists,
    Func,
    Max,
    Min,
    OuterRef,
    Q,
    QuerySet,
    Value,
    When,
    prefetch_related_objects,
)
from django.db.models.functions import Coalesce, Greatest, Lower, Upper

from apps.core.exceptions import PieceNotFound
from apps.core.selectors import whatsapp_url

from .models import Category, Collection, Material, Piece, Stone

if TYPE_CHECKING:
    from django_stubs_ext import WithAnnotations


def localized_slug(locale: str, value: str, prefix: str = "") -> Q:
    if locale == "en":
        return Q(**{f"{prefix}slug_en": value}) | (
            (Q(**{f"{prefix}slug_en": ""}) | Q(**{f"{prefix}slug_en__isnull": True}))
            & Q(**{f"{prefix}slug_es": value})
        )
    return Q(**{f"{prefix}slug_es": value})


class PriceAnnotation(TypedDict):
    effective_cents: int


def published_pieces(
    *, card_only: bool = False
) -> QuerySet[WithAnnotations[Piece, PriceAnnotation]]:
    prefetch = ("stones", "images")
    if not card_only:
        prefetch += ("materials", "collections")
    return (
        Piece.objects.filter(status=Piece.Status.PUBLISHED)
        .select_related("category")
        .prefetch_related(*prefetch)
        .annotate(
            effective_cents=Coalesce(
                "sale_price_cents", "price_cents", output_field=BigIntegerField()
            )
        )
    )


def search_piece_ids(query: str) -> list[int]:
    """Resolve each word's union once; different words may match different relations."""
    postgres = connection.vendor == "postgresql"
    if postgres:
        from django.contrib.postgres.lookups import Unaccent

    matches = Piece.objects.order_by()
    for word in query.split():
        branches = []
        for field in ("sku", "name_es", "name_en", "short_description_es", "short_description_en"):
            pieces = Piece.objects.order_by()
            if postgres:
                pieces = pieces.alias(
                    search_value=Func(Lower(field), function="catalog_immutable_unaccent")
                ).filter(
                    search_value__contains=Func(
                        Lower(Value(word)), function="catalog_immutable_unaccent"
                    )
                )
            else:
                pieces = pieces.filter(**{f"{field}__icontains": word})
            branches.append(pieces.values_list("pk", flat=True))
        lookup = "unaccent__icontains" if postgres else "icontains"
        long_text = Q(**{f"long_description_es__{lookup}": word}) | Q(
            **{f"long_description_en__{lookup}": word}
        )
        branches.append(Piece.objects.filter(long_text).order_by().values_list("pk", flat=True))
        for model, relation in (
            (Category, "category"),
            (Stone, "stones"),
            (Material, "materials"),
            (Collection, "collections"),
        ):
            if postgres:
                taxa = model.objects.alias(
                    search_es=Upper(Func("name_es", function="catalog_immutable_unaccent")),
                    search_en=Upper(Func("name_en", function="catalog_immutable_unaccent")),
                )
                normalized_word = Upper(Unaccent(Value(word)))
                names = Q(search_es__contains=normalized_word) | Q(
                    search_en__contains=normalized_word
                )
            else:
                taxa = model.objects
                names = Q(name_es__icontains=word) | Q(name_en__icontains=word)
            taxon_ids = taxa.filter(names).order_by().values("pk")
            branches.append(
                Piece.objects.filter(**{f"{relation}__in": taxon_ids})
                .order_by()
                .values_list("pk", flat=True)
            )
        if postgres:
            fuzzy = Piece.objects.alias(
                score=Greatest(
                    TrigramSimilarity(Unaccent("name_es"), Unaccent(Value(word))),
                    TrigramSimilarity(Unaccent("name_en"), Unaccent(Value(word))),
                )
            ).filter(score__gt=0.3)
            branches.append(fuzzy.order_by().values_list("pk", flat=True))
        matches = matches.filter(pk__in=branches[0].union(*branches[1:]))
    return list(matches.values_list("pk", flat=True))


def filter_pieces(
    params: dict[str, Any],
    locale: str,
    *,
    facets: bool = False,
    search_ids: list[int] | None = None,
) -> QuerySet[Piece]:
    qs = published_pieces(card_only=True)
    if params.get("availability", "available") != "all":
        qs = qs.exclude(sale_state="sold")
    if category := params.get("category"):
        categories = Category.objects.filter(localized_slug(locale, category), is_active=True)
        qs = qs.filter(Q(category__in=categories) | Q(category__parent__in=categories))
    if collection := params.get("collection"):
        qs = qs.filter(
            Exists(
                Piece.objects.filter(
                    localized_slug(locale, collection, "collections__"),
                    pk=OuterRef("pk"),
                    collections__is_active=True,
                )
            )
        )
    if material := params.get("material"):
        qs = qs.filter(
            Exists(
                Piece.objects.filter(
                    localized_slug(locale, material, "materials__"), pk=OuterRef("pk")
                )
            )
        )
    if "is_new" in params:
        qs = qs.filter(is_new=params["is_new"])
    if query := params.get("q"):
        if search_ids is None:
            search_ids = search_piece_ids(query)
        qs = qs.filter(pk__in=search_ids)
        if connection.vendor == "postgresql":
            from django.contrib.postgres.lookups import Unaccent

            qs = qs.annotate(
                similarity=Greatest(
                    TrigramSimilarity(Unaccent("name_es"), Unaccent(Value(query))),
                    TrigramSimilarity(Unaccent("name_en"), Unaccent(Value(query))),
                )
            )
    if not facets:
        if stones := params.get("stones"):
            condition = Q()
            for stone in stones:
                condition |= localized_slug(locale, stone, "stones__")
            qs = qs.filter(Exists(Piece.objects.filter(condition, pk=OuterRef("pk"))))
        if "price_min" in params:
            qs = qs.filter(effective_cents__gte=params["price_min"])
        if "price_max" in params:
            qs = qs.filter(effective_cents__lte=params["price_max"])
    sort = params.get("sort", "newest")
    ordering = {
        "newest": ["-published_at", "-pk"],
        "price_asc": ["effective_cents", "-pk"],
        "price_desc": ["-effective_cents", "-pk"],
        "featured": ["-is_new", "-published_at", "-pk"],
    }[sort]
    if params.get("q") and connection.vendor == "postgresql":
        ordering = ["-similarity", *ordering]
    return qs.order_by(*ordering)


def piece_facets(
    params: dict[str, Any], locale: str, *, search_ids: list[int] | None = None
) -> dict[str, Any]:
    qs = filter_pieces(params, locale, facets=True, search_ids=search_ids)
    ids = qs.order_by().values("pk")
    stones = Stone.objects.filter(pieces__in=ids).annotate(count=Count("pieces", distinct=True))
    price = qs.aggregate(min_cents=Min("effective_cents"), max_cents=Max("effective_cents"))
    return {
        "stones": [{"slug": stone.slug, "count": stone.count} for stone in stones],
        "price": price,
    }


def piece_detail(slug: str, locale: str) -> Piece:
    piece = (
        Piece.objects.filter(status=Piece.Status.PUBLISHED)
        .select_related("category__parent", "video")
        .filter(localized_slug(locale, slug))
        .first()
    )
    if piece is None:
        raise PieceNotFound()
    piece._detail_related = related_pieces(piece)
    prefetch_related_objects([piece, *piece._detail_related], "stones", "images")
    prefetch_related_objects([piece], "materials", "collections")
    return piece


def related_pieces(piece: Piece) -> list[Piece]:
    manual: list[Piece] = list(
        Piece.objects.filter(status=Piece.Status.PUBLISHED)
        .select_related("category__parent")
        .filter(pk__in=piece.related.values("pk"))
        .exclude(pk=piece.pk)
        .order_by(
            Case(When(sale_state="available", then=Value(0)), default=Value(1)),
            "-published_at",
            "-pk",
        )[:4]
    )
    if manual:
        return manual
    return list(
        Piece.objects.filter(status=Piece.Status.PUBLISHED)
        .select_related("category__parent")
        .filter(Q(category_id=piece.category_id) | Q(stones__in=piece.stones.all()))
        .exclude(pk=piece.pk)
        .distinct()
        .order_by(
            Case(When(sale_state="available", then=Value(0)), default=Value(1)),
            "-published_at",
            "-pk",
        )[:4]
    )


def piece_cta(piece: Piece, locale: str, config: Any = None) -> dict[str, str | None]:
    if piece.sale_state == Piece.SaleState.AVAILABLE:
        return {"kind": "add_to_cart"}
    return {
        "kind": "whatsapp",
        "reason": piece.sale_state,
        "url": whatsapp_url(piece.sale_state, piece, locale, config),
    }


def missing_english_translation() -> Q:
    """Required English fields, plus translated Spanish text with no English counterpart."""
    missing = Q()
    for field in (
        "name",
        "slug",
        "short_description",
        "long_description",
        "story",
        "care",
        "seo_title",
        "seo_description",
    ):
        empty_en = Q(**{f"{field}_en": ""}) | Q(**{f"{field}_en__isnull": True})
        if field in {"name", "slug", "short_description"}:
            missing |= empty_en
        else:
            missing |= empty_en & ~Q(**{f"{field}_es": ""}) & Q(**{f"{field}_es__isnull": False})
    return Q(status="published") & missing


def cover_data(obj: Any, locale: str | None = None) -> dict[str, Any] | None:
    """Shared taxonomy image contract, including legacy covers pending backfill."""
    from django.core.files.storage import default_storage

    cover = getattr(obj, "cover_image", None)
    if not cover:
        return None
    paths = obj.cover_renditions.get("webp", {})
    src = (
        default_storage.url(paths.get("1600") or paths[max(paths, key=int)]) if paths else cover.url
    )
    alt = getattr(obj, f"name_{locale}", "") or obj.name_es if locale else obj.name
    return {
        "src": src,
        "srcset": ", ".join(
            f"{default_storage.url(path)} {width}w"
            for width, path in sorted(paths.items(), key=lambda item: int(item[0]))
        ),
        "width": obj.cover_width or cover.width,
        "height": obj.cover_height or cover.height,
        "alt": alt,
    }
