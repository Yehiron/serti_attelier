from __future__ import annotations

from typing import Any

from drf_spectacular.utils import PolymorphicProxySerializer
from rest_framework import serializers

from apps.catalog.api.serializers import PieceListSerializer


class CmsFocalSerializer(serializers.Serializer):
    x = serializers.FloatField(min_value=0, max_value=1)
    y = serializers.FloatField(min_value=0, max_value=1)


class CmsImageSerializer(serializers.Serializer[Any]):
    focal = CmsFocalSerializer(required=False)
    src = serializers.CharField()
    srcset = serializers.CharField()
    width = serializers.IntegerField()
    height = serializers.IntegerField()
    alt = serializers.CharField()


class CtaSerializer(serializers.Serializer[Any]):
    label = serializers.CharField()  # type: ignore[assignment]
    href = serializers.CharField()
    external = serializers.BooleanField()


class SectionSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    schema_version = serializers.IntegerField()
    kind = serializers.CharField()
    title = serializers.CharField()


class HeroSlideSerializer(serializers.Serializer[Any]):
    image = CmsImageSerializer(allow_null=True)
    mobile_image = CmsImageSerializer(allow_null=True)


class StoneSerializer(serializers.Serializer[Any]):
    slug = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    image = CmsImageSerializer(allow_null=True)
    href = serializers.CharField()


class CollectionSerializer(serializers.Serializer[Any]):
    slug = serializers.CharField()
    name = serializers.CharField()
    href = serializers.CharField()


class HomeCategorySerializer(CollectionSerializer):
    image = CmsImageSerializer(allow_null=True)
    count = serializers.IntegerField()


class CmsAlternatesSerializer(serializers.Serializer[Any]):
    es = serializers.CharField()
    en = serializers.CharField()


class ProcessStepSerializer(serializers.Serializer):
    title = serializers.CharField()
    description = serializers.CharField()


class ProcessSerializer(serializers.Serializer):
    schema_version = serializers.IntegerField()
    title = serializers.CharField()
    steps = ProcessStepSerializer(many=True)


class FaqItemSerializer(serializers.Serializer):
    question = serializers.CharField()
    answer_html = serializers.CharField()


class FaqSerializer(serializers.Serializer):
    schema_version = serializers.IntegerField()
    title = serializers.CharField()
    items = FaqItemSerializer(many=True)


def section_serializers():
    from copy import deepcopy

    from apps.cms.registry import REGISTRY

    field_types = {
        "string": serializers.CharField(),
        "Image": CmsImageSerializer(),
        "Image | null": CmsImageSerializer(allow_null=True),
        "Cta | null": CtaSerializer(allow_null=True),
        "HeroSlide[]": HeroSlideSerializer(many=True),
        "StonePanel[]": StoneSerializer(many=True),
        "Named & { href: string }": CollectionSerializer(),
        "PieceCard[]": PieceListSerializer(many=True),
        "(Named & { href: string; count: number; image: Image | null })[]": HomeCategorySerializer(
            many=True
        ),
        "{ question: string; answer_html: string }[]": FaqItemSerializer(many=True),
        "{ title: string; description: string }[]": ProcessStepSerializer(many=True),
        "'left' | 'right'": serializers.ChoiceField(choices=["left", "right"]),
    }
    names = {
        "hero": "Hero",
        "statement": "Statement",
        "stone_panels": "Stones",
        "collection_rail": "Rail",
        "category_grid": "CategoryGrid",
        "story": "Story",
        "personalize": "Personalize",
        "banner": "Banner",
        "faq": "SectionFaq",
        "process": "SectionProcess",
        "image_text": "ImageText",
    }
    result = {}
    for spec in REGISTRY.values():
        fields = {
            "kind": serializers.ChoiceField(choices=[spec.kind]),
            "schema_version": serializers.ChoiceField(choices=[spec.schema_version]),
        }
        for key, value in spec.public_fields:
            field = deepcopy(field_types[value])
            field.required = not key.endswith("?")
            fields[key.rstrip("?")] = field
        name = (
            names.get(spec.kind, "".join(word.title() for word in spec.kind.split("_")))
            + "Serializer"
        )
        result[spec.kind] = type(name, (SectionSerializer,), fields)
        globals()[name] = result[spec.kind]
    return result


SECTION_SERIALIZERS = section_serializers()


class SeoSerializer(serializers.Serializer):
    title = serializers.CharField(allow_blank=True)
    description = serializers.CharField(allow_blank=True)
    image = CmsImageSerializer(allow_null=True)
    noindex = serializers.BooleanField()


class HomeSerializer(serializers.Serializer[Any]):
    seo = SeoSerializer(required=False)
    sections = PolymorphicProxySerializer(
        component_name="HomeSection",
        serializers=SECTION_SERIALIZERS,
        resource_type_field_name="kind",
        many=True,
    )
    published_at = serializers.DateTimeField(allow_null=True)
    preview = serializers.BooleanField()


class PageSerializer(serializers.Serializer[Any]):
    body_visible = serializers.BooleanField(required=False)
    seo = SeoSerializer(required=False)
    process = ProcessSerializer(required=False)
    faq = FaqSerializer(required=False)
    kind = serializers.ChoiceField(
        choices=[
            "terms",
            "privacy",
            "returns",
            "shipping",
            "cookies",
            "manufacturer",
            "personalize",
            "contact",
        ]
    )
    slug = serializers.CharField()
    title = serializers.CharField()
    body_html = serializers.CharField()
    version = serializers.IntegerField()
    updated_at = serializers.DateTimeField()
    alternates = CmsAlternatesSerializer()


class ServiceSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    title = serializers.CharField()
    description = serializers.CharField()
    image = CmsImageSerializer(allow_null=True)
    whatsapp_url = serializers.URLField(allow_null=True)


class PersonalizationSerializer(serializers.Serializer[Any]):
    services = ServiceSerializer(many=True)


class WhatsappSerializer(serializers.Serializer[Any]):
    number = serializers.CharField(allow_null=True)
    general_url = serializers.URLField(allow_null=True)


class SocialSerializer(serializers.Serializer[Any]):
    network = serializers.ChoiceField(choices=["instagram", "facebook", "tiktok", "pinterest"])
    url = serializers.URLField()


class LegalPageSerializer(serializers.Serializer[Any]):
    kind = serializers.CharField()
    title = serializers.CharField()
    href = serializers.CharField()


class SiteSettingsSerializer(serializers.Serializer[Any]):
    title_scale = serializers.FloatField()
    text_scale = serializers.FloatField()
    whatsapp = WhatsappSerializer()
    social = SocialSerializer(many=True)
    support_email = serializers.EmailField(allow_null=True)
    legal_pages = LegalPageSerializer(many=True)
    legal_versions = serializers.DictField(child=serializers.IntegerField(allow_null=True))
    certificate_price_cents = serializers.IntegerField()


class PreviewSerializer(serializers.Serializer[Any]):
    user = serializers.CharField()
    expires_at = serializers.DateTimeField()


class RedirectSerializer(serializers.Serializer):
    from_path = serializers.CharField()
    to_path = serializers.CharField()
    status_code = serializers.ChoiceField(choices=[301, 308])


class MenuItemSerializer(CtaSerializer):
    dropdown = serializers.ChoiceField(
        choices=["catalog", "stones", "collections"], allow_null=True
    )


class MenuSerializer(serializers.Serializer):
    items = MenuItemSerializer(many=True)
    preview = serializers.BooleanField()
