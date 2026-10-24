from modeltranslation.translator import TranslationOptions, register

from .models import SiteSettings


@register(SiteSettings)
class SiteSettingsTranslation(TranslationOptions):
    fields = (
        "manual_payment_instructions",
        "whatsapp_general",
        "whatsapp_preorder",
        "whatsapp_reserved",
        "whatsapp_sold",
    )
