from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django import forms
from django.contrib import admin, messages
from django.db import transaction
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin
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

    class Meta:
        model = SiteSettings
        exclude = ("id", "title_scale", "text_scale")


@admin.register(SiteSettings)
class SiteSettingsAdmin(ClientPresentationMixin, TabbedTranslationAdmin[SiteSettings], ModelAdmin):  # type: ignore[misc]  # Unfold is untyped.
    form = SiteSettingsForm

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def changelist_view(
        self, request: HttpRequest, extra_context: dict[str, Any] | None = None
    ) -> Any:
        get_solo()
        return super().changelist_view(request, extra_context)

    def get_fieldsets(self, request: HttpRequest, obj: Any = None) -> Any:
        fieldsets = super().get_fieldsets(request, obj)
        result = []
        for label, options in fieldsets:
            result.append(
                (
                    label,
                    {
                        **options,
                        "fields": [
                            field
                            for field in options["fields"]
                            if field not in {"title_scale", "text_scale"}
                        ],
                    },
                )
            )
        return result

    def changeform_view(
        self,
        request: HttpRequest,
        object_id: str | None = None,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> Any:
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
            "title_scale", "text_scale", "whatsapp_number", "instagram_url", "facebook_url",
            "tiktok_url", "pinterest_url", "support_email", "certificate_price_cents",
            "online_reservation_minutes", "manual_reservation_hours",
        }
        diff = {}
        if previous:
            for field in obj._meta.concrete_fields:
                if field.primary_key:
                    continue
                old, new = getattr(previous, field.attname), getattr(obj, field.attname)
                if old != new:
                    diff[field.name] = [old, new] if field.name in safe_fields else [
                        "[redactado]", "[redactado]"
                    ]
        save_site_settings(obj, actor=request.user)
        if diff:
            record("core.settings_updated", actor=request.user, obj=obj, diff=diff, request=request)
