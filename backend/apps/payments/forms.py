from django import forms
from unfold.widgets import UnfoldAdminFileFieldWidget, UnfoldAdminTextInputWidget


class ManualPaymentForm(forms.Form):
    reference = forms.CharField(
        label="Referencia del pago", max_length=200, widget=UnfoldAdminTextInputWidget
    )
    proof = forms.FileField(
        label="Soporte (JPEG, PNG, WebP o PDF; máximo 10 MB)", widget=UnfoldAdminFileFieldWidget
    )
