from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PaymentsConfig(AppConfig):
    name = "apps.payments"
    verbose_name = _("Pagos")

    def ready(self) -> None:
        from . import checks  # noqa: F401
