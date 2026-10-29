"""Spanish app titles while preserving third-party startup hooks and labels."""

from __future__ import annotations

from axes.apps import AppConfig as AxesConfig
from django.utils.translation import gettext_lazy as _
from django_otp.plugins.otp_totp.apps import DefaultConfig as TOTPConfig


class SpanishAxesConfig(AxesConfig):  # type: ignore[misc]
    name = "axes"
    verbose_name = _("Seguridad de acceso")


class SpanishTOTPConfig(TOTPConfig):  # type: ignore[misc]
    name = "django_otp.plugins.otp_totp"
    verbose_name = _("Verificación en dos pasos")
