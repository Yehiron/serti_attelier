from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.utils.translation import gettext as _

from apps.catalog.models import Category, Collection, PieceImage, Stone
from apps.catalog.services import rebuild_image
from apps.cms.models import HomeSection, PersonalizationService


class Command(BaseCommand):
    help = _("Regenera versiones de imágenes y limita los archivos maestros a 2400 píxeles.")

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        processed = skipped = errors = 0
        for model in (Category, Collection, Stone, PieceImage, HomeSection, PersonalizationService):
            field = (
                "original"
                if model is PieceImage
                else "cover_image"
                if model in (Category, Collection, Stone)
                else "image"
            )
            for obj in model.objects.exclude(**{field: ""}).iterator():
                try:
                    if rebuild_image(obj, dry_run=bool(options["dry_run"])):
                        processed += 1
                    else:
                        skipped += 1
                except Exception:
                    errors += 1
                    self.stderr.write(
                        _("Error al procesar %(model)s #%(pk)s.")
                        % {"model": model._meta.label, "pk": obj.pk}
                    )
        self.stdout.write(
            _("procesadas: %(processed)s / omitidas: %(skipped)s / errores: %(errors)s")
            % {"processed": processed, "skipped": skipped, "errors": errors}
        )
