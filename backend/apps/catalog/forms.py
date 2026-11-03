from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.utils.translation import gettext_lazy as _
from unfold.widgets import UnfoldAdminIntegerFieldWidget

from apps.core.admin_presentation import HELP

from .images import validated_image
from .models import Piece, PieceImage, PieceVideo


class PesosField(forms.IntegerField):
    widget = UnfoldAdminIntegerFieldWidget(attrs={"step": "0.01"})

    def prepare_value(self, value: Any) -> Any:
        return Decimal(value) / 100 if isinstance(value, (int, Decimal)) else value

    def clean(self, value: Any) -> int | None:
        pesos = forms.DecimalField(
            required=self.required,
            min_value=self.min_value() if callable(self.min_value) else self.min_value,
            max_value=self.max_value() if callable(self.max_value) else self.max_value,
            decimal_places=2,
        ).clean(value)
        return int(pesos * 100) if pesos is not None else None


if TYPE_CHECKING:
    BasePieceForm = forms.ModelForm[Piece]
    BaseImageForm = forms.ModelForm[Any]
    BaseImageFormSet = forms.BaseInlineFormSet[PieceImage, Piece]
else:
    BasePieceForm = forms.ModelForm
    BaseImageForm = forms.ModelForm
    BaseImageFormSet = forms.BaseInlineFormSet


class PieceForm(BasePieceForm):
    related = forms.ModelMultipleChoiceField(
        queryset=Piece.objects.all(),
        required=False,
        label=_("Piezas relacionadas"),
        widget=FilteredSelectMultiple(_("Piezas relacionadas"), is_stacked=False),
    )
    price_cents = PesosField(label=_("Precio (COP)"), min_value=1)
    sale_price_cents = PesosField(label=_("Precio rebajado (COP)"), min_value=1, required=False)

    class Meta:
        model = Piece
        exclude = ("status", "sale_state", "published_at", "sold_at")


class ValidatedImageForm(BaseImageForm):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            base = name.removesuffix("_es").removesuffix("_en")
            if base in HELP and not field.help_text:
                field.help_text = HELP[base]

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


class PieceImageForm(ValidatedImageForm):
    class Meta:
        model = PieceImage
        fields = "__all__"
        labels = {"original": _("Foto")}

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        if cleaned.get("is_primary") and cleaned.get("is_hover"):
            self.add_error(
                "is_hover", _("Una imagen no puede ser principal y al pasar el cursor a la vez.")
            )
        return cleaned


class PieceImageFormSet(BaseImageFormSet):
    def clean(self) -> None:
        if any(self.errors):
            return
        active = [
            form.cleaned_data
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
        ]
        if sum(bool(row.get("is_hover")) for row in active) > 1:
            raise forms.ValidationError(
                _("Selecciona solo una imagen al pasar el cursor por pieza.")
            )
        if sum(bool(row.get("is_primary")) for row in active) > 1:
            raise forms.ValidationError(_("Selecciona solo una imagen principal por pieza."))
        super().clean()


class PieceVideoForm(BaseImageForm):
    class Meta:
        model = PieceVideo
        fields = ("original", "alt")

    def clean_original(self) -> Any:
        from .videos import validate_video

        upload = self.cleaned_data.get("original")
        if not upload and self.instance.processing_status != "ready":
            raise forms.ValidationError(_("Selecciona un video."))
        if upload and not getattr(upload, "_committed", False):
            validate_video(upload)
        return upload
