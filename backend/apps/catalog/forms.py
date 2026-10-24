from typing import TYPE_CHECKING, Any

from django import forms
from django.utils.translation import gettext_lazy as _
from unfold.widgets import UnfoldAdminIntegerFieldWidget

from .images import validated_image
from .models import Piece


class PesosField(forms.IntegerField):
    widget = UnfoldAdminIntegerFieldWidget

    def prepare_value(self, value: Any) -> Any:
        return value // 100 if isinstance(value, int) else value

    def clean(self, value: Any) -> int | None:
        pesos = super().clean(value)
        return pesos * 100 if pesos is not None else None


if TYPE_CHECKING:
    BasePieceForm = forms.ModelForm[Piece]
    BaseImageForm = forms.ModelForm[Any]
else:
    BasePieceForm = forms.ModelForm
    BaseImageForm = forms.ModelForm


class PieceForm(BasePieceForm):
    related = forms.ModelMultipleChoiceField(
        queryset=Piece.objects.all(), required=False, label=_("Piezas relacionadas")
    )
    price_cents = PesosField(label=_("Precio (pesos COP)"), min_value=1)
    sale_price_cents = PesosField(
        label=_("Precio rebajado (pesos COP)"), min_value=1, required=False
    )

    class Meta:
        model = Piece
        exclude = ("status", "sale_state", "published_at", "sold_at")


class ValidatedImageForm(BaseImageForm):
    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        for name in ("original", "cover_image"):
            image = cleaned.get(name)
            if image and hasattr(image, "read"):
                try:
                    # Covers are center-cropped to 16:9 when saved; only validity is checked here.
                    validated_image(image)
                except forms.ValidationError as exc:
                    self.add_error(name, exc)
        return cleaned
