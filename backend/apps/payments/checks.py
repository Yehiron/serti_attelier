from typing import Any

from django.conf import settings
from django.core.checks import Warning, register

from .configuration import configuration_errors


@register()
def wompi_configuration(app_configs: Any, **kwargs: Any) -> list[Warning]:
    if not settings.DEBUG:
        return []
    return [Warning(message, id="payments.W001") for message in configuration_errors(settings)]
