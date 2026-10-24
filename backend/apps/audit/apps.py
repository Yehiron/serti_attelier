from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AuditConfig(AppConfig):
    name = "apps.audit"
    label = "audit"
    verbose_name = _("Auditoría")

    def ready(self) -> None:
        from . import signals  # noqa: F401
