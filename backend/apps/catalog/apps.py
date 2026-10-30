from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CatalogConfig(AppConfig):
    name = "apps.catalog"
    verbose_name = _("Catálogo")

    def ready(self) -> None:
        from .image_cleanup import register

        register()
