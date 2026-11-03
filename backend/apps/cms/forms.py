from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.catalog.images import crop_to_ratio, validated_image
from apps.core.admin_presentation import HELP

from .models import HeroSlide, HomeSection, PersonalizationService
from .services import display_ratio, validate_personalization, validate_section

if TYPE_CHECKING:
    BaseContentForm = forms.ModelForm[Any]
else:
    BaseContentForm = forms.ModelForm


class ContentForm(BaseContentForm):
    def _post_clean(self) -> None:
        super()._post_clean()  # type: ignore[misc]  # Private Django hook is absent from stubs.
        if self.errors:
            return
        obj = self.instance
        try:
            if isinstance(obj, HomeSection):
                validate_section(obj)
            elif isinstance(obj, PersonalizationService):
                validate_personalization(obj)
            if (
                isinstance(obj, (HomeSection, PersonalizationService))
                and obj.image
                and not getattr(obj.image, "_committed", True)
            ):
                image = validated_image(obj.image)
                if ratio := display_ratio(obj):
                    crop_to_ratio(image, *ratio)
        except ValidationError as exc:
            self.add_error(None, ValidationError(exc.messages))


class HeroSlideForm(BaseContentForm):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            base = name.removesuffix("_es").removesuffix("_en")
            if base in HELP and not field.help_text:
                field.help_text = HELP[base]

    # FileField leaves format validation to the shared decoder, including HEIC/AVIF.
    image = forms.FileField(
        label=_("Imagen para computador (horizontal)"),
        required=False,
        help_text=_("Horizontal, por ejemplo 1921 x 900. Opcional."),
        widget=forms.ClearableFileInput,
    )
    image_mobile = forms.FileField(
        label=_("Imagen para celular (vertical)"),
        required=False,
        help_text=_("Vertical, por ejemplo 750 x 1000. Opcional."),
        widget=forms.ClearableFileInput,
    )

    class Meta:
        model = HeroSlide
        fields = ("position", "image", "image_mobile", "alt")

    def clean(self) -> dict[str, Any]:
        data = super().clean() or {}
        for field in ("image", "image_mobile"):
            upload = data.get(field)
            if upload and not getattr(upload, "_committed", False):
                validated_image(upload)
        return data
