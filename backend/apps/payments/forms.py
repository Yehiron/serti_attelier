from django import forms


class ManualPaymentForm(forms.Form):
    reference = forms.CharField(label="Referencia del pago", max_length=200)
    proof = forms.FileField(label="Soporte (JPEG, PNG, WebP o PDF; máximo 10 MB)")
