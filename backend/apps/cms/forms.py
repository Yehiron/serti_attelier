from typing import TYPE_CHECKING, Any

from django import forms
from django.core.exceptions import ValidationError

from apps.catalog.images import crop_to_ratio, validated_image

from .models import HomeSection, PersonalizationService
from .services import validate_personalization, validate_section

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
                if isinstance(obj, PersonalizationService) or obj.kind in {
                    "hero",
                    "story",
                    "banner",
                    "personalize",
                }:
                    crop_to_ratio(image)
        except ValidationError as exc:
            self.add_error(None, ValidationError(exc.messages))
