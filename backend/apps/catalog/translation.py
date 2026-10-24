from modeltranslation.translator import TranslationOptions, register

from .models import Category, Collection, Material, Piece, PieceImage, Stone


@register([Category, Collection])
class TaxonomyTranslation(TranslationOptions):
    fields = ("name", "slug", "description", "seo_title", "seo_description")


@register(Stone)
class StoneTranslation(TranslationOptions):
    fields = ("name", "slug", "description")


@register(Material)
class MaterialTranslation(TranslationOptions):
    fields = ("name", "slug")


@register(Piece)
class PieceTranslation(TranslationOptions):
    fields = (
        "name",
        "slug",
        "short_description",
        "long_description",
        "story",
        "care",
        "seo_title",
        "seo_description",
    )


@register(PieceImage)
class ImageTranslation(TranslationOptions):
    fields = ("alt",)
    required_languages = ("es",)
