import json

from django.core.management.base import BaseCommand

from apps.cms.registry import export_registry, typescript_contract


class Command(BaseCommand):
    help = "Exporta el registro editorial o el contrato público TypeScript."

    def add_arguments(self, parser):
        parser.add_argument("--typescript", action="store_true")

    def handle(self, *args, **options):
        self.stdout.write(
            typescript_contract()
            if options["typescript"]
            else json.dumps(export_registry(), ensure_ascii=False, indent=2)
        )
