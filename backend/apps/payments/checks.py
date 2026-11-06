from typing import Any

from django.conf import settings
from django.core.checks import Warning, register

from .configuration import configuration_errors, fake_api_enabled


@register()
def wompi_configuration(app_configs: Any, **kwargs: Any) -> list[Warning]:
    if not settings.DEBUG:
        return []
    warnings = [Warning(message, id="payments.W001") for message in configuration_errors(settings)]
    if fake_api_enabled(settings):
        warnings += [
            Warning(
                "Wompi falso activo: solo desarrollo/E2E, no procesa dinero.", id="payments.W002"
            )
        ]
    return warnings
