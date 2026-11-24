from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.db.models import Case, IntegerField, When
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _
from unfold.widgets import (
    UnfoldAdminIntegerFieldWidget,
    UnfoldAdminSelectWidget,
    UnfoldAdminTextInputWidget,
)

from apps.core.admin_presentation import HELP

from .images import validated_image
from .models import Category, Piece, PieceImage, PieceVideo
from .validators import ATTRIBUTE_FIELDS


class CategoryChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj: Category) -> str:
        return f"{obj.parent.name_es} → {obj.name_es}" if obj.parent_id else str(obj.name_es)


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
    sku = forms.CharField(
        label=_("Referencia (SKU)"),
        max_length=40,
        required=False,
        help_text=_("Déjalo vacío y lo generamos (p. ej. SRT-ANI-0042). Puedes cambiarlo."),
        widget=forms.TextInput(attrs={"placeholder": "SRT-ANI-0042"}),
    )
    category = CategoryChoiceField(
        queryset=Category.objects.select_related("parent").order_by(
            Coalesce("parent__position", "position"),
            Coalesce("parent_id", "pk"),
            Case(When(parent=None, then=0), default=1, output_field=IntegerField()),
            "position",
            "pk",
        ),
        required=False,
        label=_("Categoría"),
    )
    metal = forms.CharField(label=_("Metal"), required=False, max_length=100)
    metal_purity = forms.CharField(
        label=_("Pureza"),
        required=False,
        max_length=40,
        widget=forms.TextInput(attrs={"placeholder": "18k"}),
    )
    ring_size = forms.CharField(label=_("Talla de anillo"), required=False, max_length=40)
    length_mm = forms.FloatField(
        label=_("Largo (mm)"), required=False, min_value=0.01, max_value=10000
    )
    dimensions_mm = forms.CharField(
        label=_("Dimensiones (mm)"),
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={"placeholder": "12 x 8"}),
    )
    weight_g = forms.FloatField(
        label=_("Peso (g)"), required=False, min_value=0.001, max_value=10000
    )
    carats = forms.FloatField(
        label=_("Quilates (ct)"), required=False, min_value=0.001, max_value=10000
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for key in (*ATTRIBUTE_FIELDS, "sku"):
            if key in self.fields:
                field = self.fields[key]
                attrs = {**field.widget.attrs, "class": "w-full"}
                unit = {
                    "length_mm": "mm",
                    "dimensions_mm": "mm",
                    "weight_g": "g",
                    "carats": "ct",
                }.get(key)
                if unit:
                    attrs["suffix"] = unit
                field.widget = UnfoldAdminTextInputWidget(attrs=attrs)
                if isinstance(field, forms.FloatField):
                    field.widget.input_type = "number"
                    field.widget.attrs.update(step="any", inputmode="decimal")
        if "category" in self.fields:
            self.fields["category"].widget = UnfoldAdminSelectWidget()
            self.fields["category"].widget.choices = self.fields["category"].choices
        self._original_attributes = dict(self.instance.attributes or {})
        for key in ATTRIBUTE_FIELDS:
            self.initial[key] = self._original_attributes.get(key)
        for key in ("name_es", "category", "short_description_es", "price_cents", "slug_es"):
            if key in self.fields:
                self.fields[key].help_text = (
                    str(self.fields[key].help_text or "") + " Necesario para publicar."
                )

    def clean_ring_size(self) -> Any:
        value = self.cleaned_data.get("ring_size", "")
        if value:
            try:
                number = float(value)
            except ValueError:
                return value
            if not 0 < number <= 100:
                raise forms.ValidationError("Escribe una talla mayor que cero y hasta 100.")
        return value

    def _get_validation_exclusions(self) -> set[str]:
        excluded = super()._get_validation_exclusions()
        if not self.instance.pk and not self.cleaned_data.get("sku"):
            excluded.add("sku")
        return excluded

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        attributes = dict(self._original_attributes)
        for key in ATTRIBUTE_FIELDS:
            if key not in self.fields or key in self.errors:
                continue
            value = cleaned.get(key)
            if value in (None, ""):
                attributes.pop(key, None)
            else:
                # Keep historical numeric ring sizes as numbers when unchanged.
                if key == "ring_size" and str(self._original_attributes.get(key)) == value:
                    value = self._original_attributes[key]
                attributes[key] = value
        self.instance.attributes = attributes
        return cleaned

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
        exclude = ("status", "sale_state", "published_at", "sold_at", "attributes")


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


class CategoryForm(ValidatedImageForm):
    def visibility_help(self):
        return (
            "Las categorías activas aparecen en Joyería aunque no tengan piezas ni foto. "
            "Las principales también aparecen en Comprar por categoría si esa sección "
            "está publicada. Recarga la tienda para ver los cambios. "
            "Las piezas recién publicadas pueden tardar unos minutos en aparecer."
        )

    class Meta:
        model = Category
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "is_active" in self.fields:
            self.fields["is_active"].help_text = self.visibility_help()
        if "parent" in self.fields:
            self.fields["parent"].queryset = Category.objects.filter(parent=None).exclude(
                pk=self.instance.pk
            )
            self.fields["parent"].help_text = (
                "Déjalo vacío si es una categoría principal (p. ej. Anillos). "
                "Elige una si es subcategoría (p. ej. Solitarios dentro de Anillos)."
            )


class QuickCategoryForm(forms.Form):
    name = forms.CharField(
        max_length=200, error_messages={"required": "Escribe el nombre de la categoría."}
    )
    parent = forms.ModelChoiceField(
        queryset=Category.objects.filter(parent=None, is_active=True),
        required=False,
        error_messages={
            "invalid_choice": (
                "Elige una categoría principal activa. Solo se permite un nivel de subcategorías."
            )
        },
    )


class PieceImageForm(ValidatedImageForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "original" in self.fields:
            self.fields["original"].widget = forms.FileInput(
                attrs={"class": "ca-file-input", "accept": "image/*"}
            )
        for key, label in (
            ("alt_es", "Descripción de la foto (para accesibilidad y Google)"),
            ("alt_en", "Descripción en inglés (opcional)"),
        ):
            if key in self.fields:
                self.fields[key].label = label

    class Meta:
        model = PieceImage
        fields = "__all__"
        labels = {"original": _("Foto")}

    def _get_validation_exclusions(self) -> set[str]:
        # These constraints belong to the final formset state, not the old database rows.
        excluded = super()._get_validation_exclusions()
        if getattr(self, "_photo_final_state", False):
            excluded |= {"position", "is_primary", "is_hover"}
        return excluded

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        if cleaned.get("is_primary") and cleaned.get("is_hover"):
            self.add_error(
                "is_hover", _("Una imagen no puede ser principal y al pasar el cursor a la vez.")
            )
        return cleaned


class PieceImageFormSet(BaseImageFormSet):
    def add_fields(self, form: Any, index: int | None) -> None:
        super().add_fields(form, index)
        form._photo_final_state = True

    def clean(self) -> None:
        if any(self.errors):
            return
        from .services import validate_photo_state

        active = [
            form.instance
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
        ]
        validate_photo_state(self.instance, active)
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
