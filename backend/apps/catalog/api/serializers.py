from __future__ import annotations

from typing import Any

from django.core.files.storage import default_storage
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.core.money import Money
from apps.core.selectors import piece_url, whatsapp_url

from ..models import Category, Collection, Material, Piece, PieceImage, Stone
from ..selectors import cover_data, piece_cta, related_pieces


class MoneySerializer(serializers.Serializer[Any]):
    amount_cents = serializers.IntegerField()
    currency = serializers.CharField(default="COP")


class NamedSerializer(serializers.Serializer[Any]):
    slug = serializers.CharField()
    name = serializers.CharField()


class StoneNamedSerializer(NamedSerializer):
    color = serializers.CharField(allow_blank=True)


class MaterialNamedSerializer(NamedSerializer):
    color = serializers.CharField(allow_blank=True)


class CoverSerializer(serializers.Serializer[Any]):
    src = serializers.CharField()
    srcset = serializers.CharField()
    width = serializers.IntegerField()
    height = serializers.IntegerField()
    alt = serializers.CharField()


class TaxonSerializer(NamedSerializer):
    updated_at = serializers.DateTimeField(read_only=True)
    description = serializers.CharField(default="", allow_blank=True)
    seo_title = serializers.CharField(default="", allow_blank=True)
    seo_description = serializers.CharField(default="", allow_blank=True)
    slugs = serializers.SerializerMethodField()
    cover = serializers.SerializerMethodField()

    @extend_schema_field(serializers.DictField(child=serializers.CharField()))
    def get_slugs(self, obj: Category | Collection | Stone | Material) -> dict[str, str]:
        return {"es": obj.slug_es, "en": obj.slug_en or obj.slug_es}

    @extend_schema_field(CoverSerializer(allow_null=True))
    def get_cover(self, obj: Category | Collection | Stone | Material) -> dict[str, Any] | None:
        return cover_data(obj)

    cover_image = serializers.SerializerMethodField()

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_cover_image(self, obj: Category | Collection | Stone | Material) -> str | None:
        cover = cover_data(obj)
        return str(cover["src"]) if cover else None


class StoneTaxonSerializer(TaxonSerializer):
    color = serializers.CharField(allow_blank=True)


class MaterialTaxonSerializer(TaxonSerializer):
    color = serializers.CharField(allow_blank=True)


class CategorySerializer(TaxonSerializer):
    children = serializers.SerializerMethodField()

    @extend_schema_field(TaxonSerializer(many=True))
    def get_children(self, obj: Category) -> list[dict[str, Any]]:
        return list(
            TaxonSerializer(
                [child for child in obj.children.all() if child.is_active and child.slug], many=True
            ).data
        )


class TaxonomySerializer(serializers.Serializer[Any]):
    categories = CategorySerializer(many=True)
    collections = TaxonSerializer(many=True)
    stones = StoneTaxonSerializer(many=True)
    materials = MaterialTaxonSerializer(many=True)


class ImageSerializer(serializers.Serializer[Any]):
    src = serializers.SerializerMethodField()
    srcset = serializers.SerializerMethodField()
    width = serializers.IntegerField()
    height = serializers.IntegerField()
    alt = serializers.CharField()

    @extend_schema_field(serializers.CharField())
    def get_src(self, obj: PieceImage) -> str:
        paths = obj.renditions.get("webp", {})
        if paths:
            key = "960" if "960" in paths else max(paths, key=int)
            return str(default_storage.url(paths[key]))
        return str(obj.original.url)

    @extend_schema_field(serializers.CharField())
    def get_srcset(self, obj: PieceImage) -> str:
        return ", ".join(
            f"{default_storage.url(path)} {width}w"
            for width, path in sorted(
                obj.renditions.get("webp", {}).items(), key=lambda item: int(item[0])
            )
        )


class PieceListSerializer(serializers.ModelSerializer[Piece]):
    category = serializers.SerializerMethodField()
    stones = StoneNamedSerializer(many=True)
    price = serializers.SerializerMethodField()
    sale_price = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    hover_image = serializers.SerializerMethodField()
    alternates = serializers.SerializerMethodField()

    class Meta:
        model = Piece
        fields: tuple[str, ...] = (
            "slug",
            "sku",
            "name",
            "category",
            "stones",
            "price",
            "sale_price",
            "sale_state",
            "is_new",
            "image",
            "hover_image",
            "alternates",
        )

    @extend_schema_field(serializers.DictField(child=serializers.CharField()))
    def get_alternates(self, obj: Piece) -> dict[str, str]:
        return {locale: piece_url(obj, locale) for locale in ("es", "en")}

    @extend_schema_field(NamedSerializer(allow_null=True))
    def get_category(self, obj: Piece) -> dict[str, str] | None:
        return (
            dict(NamedSerializer(obj.category).data)
            if obj.category and obj.category.is_active
            else None
        )

    @extend_schema_field(MoneySerializer)
    def get_price(self, obj: Piece) -> dict[str, int | str]:
        return Money(obj.price_cents).as_dict()

    @extend_schema_field(MoneySerializer(allow_null=True))
    def get_sale_price(self, obj: Piece) -> dict[str, int | str] | None:
        return Money(obj.sale_price_cents).as_dict() if obj.sale_price_cents is not None else None

    @extend_schema_field(ImageSerializer(allow_null=True))
    def get_image(self, obj: Piece) -> dict[str, Any] | None:
        image = next(
            (
                image
                for image in obj.images.all()
                if image.is_primary and image.processing_status == "ready"
            ),
            None,
        )
        return dict(ImageSerializer(image).data) if image else None

    @extend_schema_field(ImageSerializer(allow_null=True))
    def get_hover_image(self, obj: Piece) -> dict[str, Any] | None:
        image = next(
            (
                image
                for image in obj.images.all()
                if image.is_hover and image.processing_status == "ready"
            ),
            None,
        )
        return dict(ImageSerializer(image).data) if image else None


class CTASerializer(serializers.Serializer[Any]):
    kind = serializers.ChoiceField(choices=["add_to_cart", "whatsapp"])
    reason = serializers.ChoiceField(choices=["reserved", "preorder", "sold"], required=False)
    url = serializers.URLField(allow_null=True, required=False)


class AlternatesSerializer(serializers.Serializer[Any]):
    es = serializers.URLField()
    en = serializers.URLField()


class SEOSerializer(serializers.Serializer[Any]):
    title = serializers.CharField()
    description = serializers.CharField()
    alternates = AlternatesSerializer()


class VideoSerializer(serializers.Serializer[Any]):
    src = serializers.CharField()
    type = serializers.ChoiceField(choices=["video/mp4"])
    width = serializers.IntegerField()
    height = serializers.IntegerField()
    duration_seconds = serializers.FloatField()
    alt = serializers.CharField()
    poster = CoverSerializer()


class PieceDetailSerializer(PieceListSerializer):
    video = serializers.SerializerMethodField()
    materials = MaterialNamedSerializer(many=True)
    collections = serializers.SerializerMethodField()
    gallery = serializers.SerializerMethodField()
    related = serializers.SerializerMethodField()
    seo = serializers.SerializerMethodField()
    cta = serializers.SerializerMethodField()
    whatsapp_url = serializers.SerializerMethodField()

    class Meta(PieceListSerializer.Meta):
        fields = (
            *PieceListSerializer.Meta.fields,
            "video",
            "updated_at",
            "published_at",
            "piece_number",
            "short_description",
            "long_description",
            "story",
            "care",
            "attributes",
            "materials",
            "collections",
            "gallery",
            "related",
            "seo",
            "cta",
            "whatsapp_url",
        )

    @extend_schema_field(VideoSerializer(allow_null=True))
    def get_video(self, obj: Piece) -> dict[str, Any] | None:
        video = getattr(obj, "video", None)
        if video is None or video.processing_status != "ready":
            return None
        paths = video.poster_renditions.get("webp", {})
        return {
            "src": video.mp4.url,
            "type": "video/mp4",
            "width": video.width,
            "height": video.height,
            "duration_seconds": video.duration_seconds,
            "alt": video.alt,
            "poster": {
                "src": video.poster.url,
                "srcset": ", ".join(
                    f"{default_storage.url(path)} {width}w"
                    for width, path in sorted(paths.items(), key=lambda item: int(item[0]))
                ),
                "width": video.width,
                "height": video.height,
                "alt": video.alt,
            },
        }

    @extend_schema_field(NamedSerializer(many=True))
    def get_collections(self, obj: Piece) -> list[dict[str, Any]]:
        return list(
            NamedSerializer(
                [collection for collection in obj.collections.all() if collection.is_active],
                many=True,
            ).data
        )

    @extend_schema_field(ImageSerializer(many=True))
    def get_gallery(self, obj: Piece) -> list[dict[str, Any]]:
        return list(
            ImageSerializer(
                [image for image in obj.images.all() if image.processing_status == "ready"],
                many=True,
            ).data
        )

    @extend_schema_field(PieceListSerializer(many=True))
    def get_related(self, obj: Piece) -> list[dict[str, Any]]:
        related = getattr(obj, "_detail_related", None)
        return list(
            PieceListSerializer(
                related if related is not None else related_pieces(obj), many=True
            ).data
        )

    @extend_schema_field(SEOSerializer)
    def get_seo(self, obj: Piece) -> dict[str, Any]:
        return {
            "title": obj.seo_title or "",
            "description": obj.seo_description or "",
            "alternates": {locale: piece_url(obj, locale) for locale in ("es", "en")},
        }

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_whatsapp_url(self, obj: Piece) -> str | None:
        return whatsapp_url("general", obj, self.context["locale"], self.context.get("settings"))

    @extend_schema_field(CTASerializer)
    def get_cta(self, obj: Piece) -> dict[str, Any]:
        return piece_cta(obj, self.context["locale"], self.context.get("settings"))


class CatalogFiltersSerializer(serializers.Serializer[Any]):
    locale = serializers.ChoiceField(choices=["es", "en"], required=False)
    category = serializers.CharField(required=False)
    collection = serializers.CharField(required=False)
    stone = serializers.CharField(required=False)
    material = serializers.CharField(required=False)
    price_min = serializers.IntegerField(min_value=0, required=False)
    price_max = serializers.IntegerField(min_value=0, required=False)
    availability = serializers.ChoiceField(choices=["available", "all"], default="available")
    is_new = serializers.BooleanField(required=False)
    q = serializers.CharField(required=False, max_length=200)
    sort = serializers.ChoiceField(
        choices=["newest", "price_asc", "price_desc", "featured"], default="newest"
    )
    page = serializers.IntegerField(min_value=1, required=False)
    page_size = serializers.IntegerField(min_value=1, required=False)


class StoneFacetSerializer(serializers.Serializer[Any]):
    slug = serializers.CharField()
    count = serializers.IntegerField()


class PriceFacetSerializer(serializers.Serializer[Any]):
    min_cents = serializers.IntegerField(allow_null=True)
    max_cents = serializers.IntegerField(allow_null=True)


class FacetsSerializer(serializers.Serializer[Any]):
    stones = StoneFacetSerializer(many=True)
    price = PriceFacetSerializer()


class CatalogListSerializer(serializers.Serializer[Any]):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = PieceListSerializer(many=True)
    facets = FacetsSerializer()
