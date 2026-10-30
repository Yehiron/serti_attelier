from __future__ import annotations

from modeltranslation.translator import TranslationOptions, register

from .models import HeroSlide, HomeSection, Page, PersonalizationService


@register(HomeSection)
class SectionTranslation(TranslationOptions):
    fields = ("title", "subtitle", "body", "image_alt", "cta_label")


@register(Page)
class PageTranslation(TranslationOptions):
    fields = ("title", "slug", "body")
    required_languages = ("es",)


@register(PersonalizationService)
class ServiceTranslation(TranslationOptions):
    fields = ("title", "description", "whatsapp_message", "image_alt")


@register(HeroSlide)
class HeroSlideTranslation(TranslationOptions):
    fields = ("alt",)
