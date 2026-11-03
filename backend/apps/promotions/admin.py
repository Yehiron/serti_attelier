from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django import forms
from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from apps.catalog.forms import PesosField
from apps.core.admin_presentation import ClientPresentationMixin
from apps.core.formatting import format_admin_cop

from .models import Coupon
from .services import delete_coupon, save_coupon

if TYPE_CHECKING:
    BaseCouponForm = forms.ModelForm[Coupon]
else:
    BaseCouponForm = forms.ModelForm


class CouponForm(BaseCouponForm):
    min_subtotal_cents = PesosField(label=_("Compra mínima (COP)"), min_value=0)
    amount = forms.DecimalField(
        label=_("Valor (% o pesos)"), min_value=Decimal("0.01"), decimal_places=2
    )

    class Meta:
        model = Coupon
        fields = (
            "code",
            "kind",
            "amount",
            "starts_at",
            "ends_at",
            "max_uses",
            "max_uses_per_email",
            "min_subtotal_cents",
            "applies_to_sale_items",
            "categories",
            "collections",
            "is_active",
        )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["amount"].initial = (
                self.instance.value
                if self.instance.kind == "percent"
                else Decimal(self.instance.value) / 100
            )

    def clean(self) -> dict[str, Any]:
        data = super().clean() or {}
        amount = data.get("amount")
        if amount is not None:
            if data.get("kind") == "percent":
                if amount != int(amount) or not 1 <= amount <= 90:
                    self.add_error("amount", _("Usa un porcentaje entero entre 1 y 90."))
                self.instance.value = int(amount)
            else:
                self.instance.value = int(amount * 100)
        self.instance.code = str(data.get("code", "")).strip().upper()
        data["code"] = self.instance.code
        return data


@admin.register(Coupon)
class CouponAdmin(ClientPresentationMixin, ModelAdmin):  # type: ignore[misc]
    form = CouponForm
    list_display = ("code", "kind", "formatted_value", "is_active", "starts_at", "ends_at")
    list_filter = ("kind", "is_active")
    search_fields = ("code",)
    filter_horizontal = ("categories", "collections")

    @admin.display(description=_("Valor"))
    def formatted_value(self, obj: Coupon) -> str:
        return f"{obj.value}%" if obj.kind == "percent" else format_admin_cop(obj.value)

    def save_model(self, request: HttpRequest, obj: Coupon, form: Any, change: bool) -> None:
        save_coupon(
            obj,
            request=request,
            relations={name: form.cleaned_data[name] for name in ("categories", "collections")},
        )

    def save_related(self, request: HttpRequest, form: Any, formsets: Any, change: bool) -> None:
        # All fields and M2M relations are persisted by the atomic service above.
        pass

    def delete_model(self, request: HttpRequest, obj: Coupon) -> None:
        delete_coupon(obj, request=request)

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[Coupon]) -> None:
        for coupon in queryset.order_by("pk"):
            delete_coupon(coupon, request=request)
