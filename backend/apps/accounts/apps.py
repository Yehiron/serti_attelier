from typing import Any

from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    label = "accounts"
    verbose_name = _("Cuentas")

    def ready(self) -> None:
        post_migrate.connect(sync_after_migrate, sender=self, dispatch_uid="accounts.sync_roles")


def sync_after_migrate(**kwargs: Any) -> None:
    from .services import sync_roles

    sync_roles(using=kwargs["using"])
