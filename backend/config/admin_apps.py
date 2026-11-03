"""Spanish app titles while preserving third-party startup hooks and labels."""

from __future__ import annotations

from axes.apps import AppConfig as AxesConfig
from django.contrib.admin.apps import AdminConfig
from django.utils.translation import gettext_lazy as _
from django_otp.plugins.otp_totp.apps import DefaultConfig as TOTPConfig


class SpanishAxesConfig(AxesConfig):  # type: ignore[misc]
    name = "axes"
    verbose_name = _("Seguridad de acceso")


class SpanishTOTPConfig(TOTPConfig):  # type: ignore[misc]
    name = "django_otp.plugins.otp_totp"
    verbose_name = _("Verificación en dos pasos")

    def ready(self) -> None:
        super().ready()
        # Upstream uses literal English labels; keep its migration options intact.
        model = self.get_model("TOTPDevice")
        model._meta.verbose_name = _("dispositivo de verificación")
        model._meta.verbose_name_plural = _("dispositivos de verificación")


class ClientAdminConfig(AdminConfig):
    def ready(self) -> None:
        super().ready()
        from django.contrib import admin

        from apps.core.dashboard import configure_technical_admins

        admin.site.index_title = _("Inicio")
        configure_technical_admins()
