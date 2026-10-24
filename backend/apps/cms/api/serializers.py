from typing import Any

from drf_spectacular.utils import PolymorphicProxySerializer
from rest_framework import serializers

from apps.catalog.api.serializers import PieceListSerializer


class CmsImageSerializer(serializers.Serializer[Any]):
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
    kind = serializers.CharField()
    title = serializers.CharField()


class HeroSerializer(SectionSerializer):
    subtitle = serializers.CharField()
    image = CmsImageSerializer(allow_null=True)
    cta = CtaSerializer(allow_null=True)


class StatementSerializer(SectionSerializer):
    body = serializers.CharField()


class EditorialSerializer(StatementSerializer):
    image = CmsImageSerializer(allow_null=True)
    cta = CtaSerializer(allow_null=True)


class StoneSerializer(serializers.Serializer[Any]):
    slug = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    image = CmsImageSerializer(allow_null=True)
    href = serializers.CharField()


class StonesSerializer(SectionSerializer):
    subtitle = serializers.CharField()
    stones = StoneSerializer(many=True)


class CollectionSerializer(serializers.Serializer[Any]):
    slug = serializers.CharField()
    name = serializers.CharField()
    href = serializers.CharField()


class RailSerializer(SectionSerializer):
    subtitle = serializers.CharField()
    collection = CollectionSerializer()
    pieces = PieceListSerializer(many=True)


class HomeSerializer(serializers.Serializer[Any]):
    sections = PolymorphicProxySerializer(
        component_name="HomeSection",
        serializers={
            "hero": HeroSerializer,
            "statement": StatementSerializer,
            "stone_panels": StonesSerializer,
            "collection_rail": RailSerializer,
            "story": EditorialSerializer,
            "personalize": EditorialSerializer,
            "banner": EditorialSerializer,
        },
        resource_type_field_name="kind",
        many=True,
    )
    published_at = serializers.DateTimeField(allow_null=True)
    preview = serializers.BooleanField()


class CmsAlternatesSerializer(serializers.Serializer[Any]):
    es = serializers.CharField()
    en = serializers.CharField()


class PageSerializer(serializers.Serializer[Any]):
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
    whatsapp = WhatsappSerializer()
    social = SocialSerializer(many=True)
    support_email = serializers.EmailField(allow_null=True)
    legal_pages = LegalPageSerializer(many=True)


class PreviewSerializer(serializers.Serializer[Any]):
    user = serializers.CharField()
    expires_at = serializers.DateTimeField()
