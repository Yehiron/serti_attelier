"""Conservative local CMS collector; no catalog paths or symlinks are followed."""

from datetime import timedelta
from pathlib import Path
from urllib.parse import unquote, urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.audit.services import record
from apps.cms.media import all_usage, used_by
from apps.cms.models import MediaAsset


def collect(*, execute=False):
    root = Path(settings.MEDIA_ROOT).resolve()
    folder = root / "cms"
    cutoff = timezone.now() - timedelta(hours=24)
    candidates = []
    with transaction.atomic():
        assets = list(MediaAsset.objects.select_for_update(of=("self",)).all())
        sources = all_usage()
        retained = set()

        def paths(value):
            if isinstance(value, dict):
                for item in value.values():
                    paths(item)
            elif isinstance(value, list):
                for item in value:
                    paths(item)
            elif isinstance(value, str):
                for item in value.split(", "):
                    item = item.split(" ")[0]
                    if item.startswith(settings.MEDIA_URL):
                        item = unquote(urlsplit(item).path[len(settings.MEDIA_URL) :])
                    if item.startswith("cms/"):
                        retained.add(item)

        for _, _, source in sources:
            paths(source)
        for asset in assets:
            if (
                asset.created_at >= cutoff
                or asset.archived
                or asset.title
                or asset.tags
                or asset.alt_es
                or asset.alt_en
                or used_by(asset, sources)
            ):
                paths(asset.original.name)
                paths(asset.versions)
            elif execute:
                record("cms.media_orphan_removed", obj=asset)
                asset.delete()
        if folder.is_dir() and not folder.is_symlink():
            for file in folder.rglob("*"):
                if not file.is_file() or file.is_symlink():
                    continue
                # A symlink in any ancestor must not escape MEDIA_ROOT/cms.
                resolved = file.resolve()
                if not resolved.is_relative_to(folder) or file != resolved:
                    continue
                relative = file.relative_to(root).as_posix()
                if relative in retained or file.stat().st_mtime >= cutoff.timestamp():
                    continue
                candidates.append(relative)
                if execute:
                    record("cms.media_file_deleted", diff={"Archivo CMS": [relative, "Eliminado"]})
                    file.unlink()
    return candidates


class Command(BaseCommand):
    help = "Muestra fotos CMS huérfanas de más de 24 horas. Usa --execute para borrarlas."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--dry-run", action="store_true")
        group.add_argument("--execute", action="store_true")

    def handle(self, *args, **options):
        candidates = collect(execute=options["execute"])
        self.stdout.write("Borrado" if options["execute"] else "Simulación: no se borró nada")
        for path in candidates:
            self.stdout.write(path)
        self.stdout.write(f"{len(candidates)} archivos huérfanos.")
