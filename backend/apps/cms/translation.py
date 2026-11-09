from __future__ import annotations

from modeltranslation.translator import TranslationOptions, register

from .models import FaqItem, HeroSlide, HomeSection, Page, PersonalizationService, ProcessStep


@register(HomeSection)
class SectionTranslation(TranslationOptions):
    fields = ("title", "subtitle", "body", "image_alt", "cta_label")


@register(Page)
class PageTranslation(TranslationOptions):
    fields = ("title", "slug", "body", "process_title", "faq_title")
    required_languages = ("es",)


@register(PersonalizationService)
class ServiceTranslation(TranslationOptions):
    fields = ("title", "description", "whatsapp_message", "image_alt")


@register(HeroSlide)
class HeroSlideTranslation(TranslationOptions):
    fields = ("alt",)


@register(ProcessStep)
class ProcessStepTranslation(TranslationOptions):
    fields = ("title", "description")
    required_languages = ("es",)


@register(FaqItem)
class FaqItemTranslation(TranslationOptions):
    fields = ("question", "answer")
    required_languages = ("es",)
