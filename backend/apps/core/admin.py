from __future__ import annotations

from string import Formatter
from typing import TYPE_CHECKING, Any

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

# The redesigned form draws its own ES/EN tabs (core/settings.js); the tabbed variant needs
# jQuery UI tabs, which the dashboard does not load (it raised «tabsContainer.tabs»).
from modeltranslation.admin import TranslationAdmin
from unfold.admin import ModelAdmin

from apps.audit.services import record
from apps.catalog.forms import PesosField

from .admin_presentation import ClientPresentationMixin
from .models import Department, Municipality, SiteSettings
from .selectors import get_solo
from .services import save_site_settings


class ReadOnlyAdmin(ModelAdmin):  # type: ignore[misc]  # Unfold is untyped.
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(Department, Municipality)
class LocationAdmin(ReadOnlyAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return request.user.is_active and request.user.is_staff


if TYPE_CHECKING:
    BaseSettingsForm = forms.ModelForm[SiteSettings]
else:
    BaseSettingsForm = forms.ModelForm


class SiteSettingsForm(BaseSettingsForm):
    certificate_price_cents = PesosField(label=_("Precio del certificado (COP)"), min_value=0)

    def clean(self) -> dict[str, Any]:
        cleaned: dict[str, Any] = super().clean() or {}
        for prefix, allowed in (
            ("whatsapp", {"name", "sku", "url"}),
            ("manual_payment_instructions", {"number", "total", "deadline"}),
        ):
            names = (
                [
                    f"whatsapp_{kind}_{locale}"
                    for kind in ("general", "preorder", "reserved", "sold")
                    for locale in ("es", "en")
                ]
                if prefix == "whatsapp"
                else [f"{prefix}_{locale}" for locale in ("es", "en")]
            )
            for name in names:
                if name not in cleaned:
                    continue
                try:
                    for _literal, field, spec, conversion in Formatter().parse(cleaned[name] or ""):
                        if field is not None and (field not in allowed or spec or conversion):
                            raise ValueError
                except ValueError:
                    self.add_error(
                        name,
                        _("Solo se permiten {name}, {sku} y {url}.")
                        if prefix == "whatsapp"
                        else _("Solo se permiten {number}, {total} y {deadline}."),
                    )
        return cleaned

    class Meta:
        model = SiteSettings
        exclude = ("id", "title_scale", "text_scale")


@admin.register(SiteSettings)
class SiteSettingsAdmin(ClientPresentationMixin, TranslationAdmin[SiteSettings], ModelAdmin):  # type: ignore[misc]  # Unfold is untyped.
    form = SiteSettingsForm
    change_form_template = "admin/core/sitesettings/change_form.html"

    class Media:
        css = {"all": ("core/settings.css",)}
        js = ("core/settings.js",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def changelist_view(
        self, request: HttpRequest, extra_context: dict[str, Any] | None = None
    ) -> Any:
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied
        obj = get_solo()
        return redirect(
            reverse(
                "admin:core_sitesettings_change", args=[obj.pk], current_app=self.admin_site.name
            )
        )

    def get_fieldsets(self, request: HttpRequest, obj: Any = None) -> Any:
        return (
            (
                _("Contacto y redes"),
                {
                    "fields": (
                        "whatsapp_number",
                        "support_email",
                        "instagram_url",
                        "facebook_url",
                        "tiktok_url",
                        "pinterest_url",
                        "appointment_only",
                    )
                },
            ),
            (
                _("Mensajes de WhatsApp"),
                {
                    "fields": tuple(
                        f"whatsapp_{kind}_{lang}"
                        for kind in ("general", "preorder", "reserved", "sold")
                        for lang in ("es", "en")
                    )
                },
            ),
            (
                _("Pagos y reservas"),
                {
                    "fields": (
                        "certificate_price_cents",
                        "online_reservation_minutes",
                        "manual_reservation_hours",
                        "manual_payment_instructions_es",
                        "manual_payment_instructions_en",
                    )
                },
            ),
            (
                _("Google (SEO)"),
                {
                    "fields": (
                        "seo_home_title_es",
                        "seo_home_title_en",
                        "seo_home_description_es",
                        "seo_home_description_en",
                    )
                },
            ),
            (
                _("Horario y zona"),
                {
                    "fields": (
                        "business_locality",
                        "business_region",
                        "business_country",
                        "service_area",
                        "opening_hours_es",
                        "opening_hours_en",
                    )
                },
            ),
        )

    def changeform_view(
        self,
        request: HttpRequest,
        object_id: str | None = None,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> Any:
        from django.conf import settings

        from apps.catalog.models import Piece

        from .selectors import piece_url

        piece = Piece.objects.filter(status=Piece.Status.PUBLISHED).order_by("pk").first()
        example = (
            {"name": piece.name_es, "sku": piece.sku, "url": piece_url(piece, "es")}
            if piece
            else {
                "name": "Anillo Halo de Esmeralda",
                "sku": "SERTI-001",
                "url": f"{settings.PUBLIC_SITE_URL}/es/piezas/ejemplo",
            }
        )
        extra_context = {
            **(extra_context or {}),
            "settings_example": example,
            "settings_site_url": settings.PUBLIC_SITE_URL,
        }
        if not get_solo().whatsapp_number:
            self.message_user(
                request,
                _("Falta el número de WhatsApp: el botón flotante no se muestra"),
                messages.WARNING,
            )
        return super().changeform_view(request, object_id, form_url, extra_context)

    @transaction.atomic
    def save_model(self, request: HttpRequest, obj: SiteSettings, form: Any, change: bool) -> None:
        previous = SiteSettings.objects.filter(pk=obj.pk).first()
        # Only explicitly approved settings can enter the audit log. New fields are redacted.
        safe_fields = {
            "title_scale",
            "text_scale",
            "whatsapp_number",
            "instagram_url",
            "facebook_url",
            "tiktok_url",
            "pinterest_url",
            "support_email",
            "certificate_price_cents",
            "online_reservation_minutes",
            "manual_reservation_hours",
        }
        diff = {}
        if previous:
            for field in obj._meta.concrete_fields:
                if field.primary_key:
                    continue
                old, new = getattr(previous, field.attname), getattr(obj, field.attname)
                if old != new:
                    diff[field.name] = (
                        [old, new] if field.name in safe_fields else ["[redactado]", "[redactado]"]
                    )
        save_site_settings(obj, actor=request.user)
        if diff:
            record("core.settings_updated", actor=request.user, obj=obj, diff=diff, request=request)
