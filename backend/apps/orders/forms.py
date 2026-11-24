from __future__ import annotations

from django import forms
from django.core.validators import URLValidator
from django.utils.translation import gettext_lazy as _
from unfold.widgets import (
    UnfoldAdminSelectWidget,
    UnfoldAdminTextareaWidget,
    UnfoldAdminTextInputWidget,
    UnfoldAdminURLInputWidget,
)

from .models import Order


class FulfillmentForm(forms.Form):
    notify = forms.BooleanField(label="Avisar al cliente", required=False, initial=False)
    target = forms.ChoiceField(
        label=_("Estado de entrega"),
        choices=Order._meta.get_field("fulfillment_status").choices or [],
        widget=UnfoldAdminSelectWidget,
    )
    note = forms.CharField(
        label=_("Nota interna"), required=False, max_length=2000, widget=UnfoldAdminTextareaWidget
    )
    carrier = forms.CharField(
        label=_("Transportadora (obligatoria al enviar)"),
        max_length=200,
        required=False,
        widget=UnfoldAdminTextInputWidget,
    )
    tracking_number = forms.CharField(
        label=_("Número de seguimiento"),
        max_length=200,
        required=False,
        widget=UnfoldAdminTextInputWidget,
    )
    tracking_url = forms.URLField(
        label=_("Enlace de seguimiento"),
        assume_scheme="https",
        required=False,
        widget=UnfoldAdminURLInputWidget,
        validators=[URLValidator(schemes=["https"])],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["target"].choices = [
            (k, v) for k, v in self.fields["target"].choices if k != "cancelled"
        ]

    def clean_carrier(self) -> str:
        value: str = self.cleaned_data["carrier"].strip()
        if self.cleaned_data.get("target") == "shipped" and not value:
            raise forms.ValidationError(_("Indica la transportadora antes de enviar."))
        return value


class CardStateSelect(UnfoldAdminSelectWidget):
    disable_preparing = False

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if str(value) == "preparing" and self.disable_preparing:
            option["attrs"]["disabled"] = True
        return option


class CardFulfillmentForm(FulfillmentForm):
    notify = forms.BooleanField(
        label="Enviar notificación al cliente por correo", required=False, initial=True
    )
    include_reason = forms.BooleanField(
        label="Incluir motivo en el correo de cancelación", required=False, initial=False
    )
    expected_status = forms.CharField(max_length=12, widget=forms.HiddenInput)

    def __init__(self, *args, order, can_cancel=False, **kwargs):
        from .services import available_fulfillment_transitions

        super().__init__(*args, **kwargs)
        self.order_payment_unapproved = order.payment_status != "approved"
        allowed = available_fulfillment_transitions(order)
        # Swap the widget first: assigning choices also copies them onto the current widget.
        self.fields["target"].widget = CardStateSelect()
        self.fields["target"].choices = [
            (key, label)
            for key, label in Order._meta.get_field("fulfillment_status").choices
            if key in allowed and (key != "cancelled" or can_cancel)
            and not (key in {"preparing", "shipped"} and order.payment_status != "approved")
        ]
        self.fields["target"].widget.disable_preparing = order.payment_status != "approved"
        self.fields["expected_status"].initial = order.fulfillment_status
        if (self.is_bound and self.data.get("target") in {"preparing", "shipped"}
                and order.payment_status != "approved"):
            self.fields["target"].choices += [(self.data["target"], "")]
        if not order.customer_email.strip():
            self.fields["notify"].disabled = True
            self.fields["notify"].initial = False

    def clean_target(self):
        target = self.cleaned_data["target"]
        if target in {"preparing", "shipped"} and self.order_payment_unapproved:
            raise forms.ValidationError("No puedes preparar un pedido sin pago aprobado.")
        return target
