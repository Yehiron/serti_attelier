from django import forms
from django.core.validators import URLValidator
from django.utils.translation import gettext_lazy as _

from .models import Order


class FulfillmentForm(forms.Form):
    target = forms.ChoiceField(
        label=_("Estado operativo"),
        choices=Order._meta.get_field("fulfillment_status").choices or [],
    )
    note = forms.CharField(
        label=_("Nota interna"), required=False, max_length=2000, widget=forms.Textarea
    )
    carrier = forms.CharField(
        label=_("Transportadora (obligatoria al enviar)"), max_length=200, required=False
    )
    tracking_number = forms.CharField(
        label=_("Número de seguimiento"), max_length=200, required=False
    )
    tracking_url = forms.URLField(
        label=_("Enlace de seguimiento"),
        assume_scheme="https",
        required=False,
        validators=[URLValidator(schemes=["https"])],
    )

    def clean_carrier(self) -> str:
        value: str = self.cleaned_data["carrier"].strip()
        if self.cleaned_data.get("target") == "shipped" and not value:
            raise forms.ValidationError(_("Indica la transportadora antes de enviar."))
        return value
