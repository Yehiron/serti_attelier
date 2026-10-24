from typing import Any

from django.core.management.base import BaseCommand

from apps.accounts.services import sync_roles


class Command(BaseCommand):
    help = "Sincroniza los permisos de los roles de SERTI."

    def handle(self, *args: Any, **options: Any) -> None:
        sync_roles()
        self.stdout.write(self.style.SUCCESS("Roles sincronizados."))
