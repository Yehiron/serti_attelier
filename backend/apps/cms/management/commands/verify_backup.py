"""Read-only verification against an explicitly selected temporary database."""

import json
import re
from pathlib import Path
from typing import Any, cast
from urllib.parse import unquote, urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = "Comprueba una copia restaurada temporal; nunca restaura ni modifica la base real."

    def add_arguments(self, parser):
        parser.add_argument("--database-name", required=True)
        parser.add_argument("--media-root", required=True)
        parser.add_argument("--private-media-root", required=True)

    def handle(self, *args, **options):
        name = options["database_name"]
        if (
            not re.fullmatch(r"serti_verify_[0-9]+_[0-9]+", name)
            or name == connection.settings_dict["NAME"]
        ):
            raise CommandError("Solo se permite una base temporal de verificación.")
        connection.close()
        connection.settings_dict = {**connection.settings_dict, "NAME": name}
        media = Path(options["media_root"]).resolve()
        private = Path(options["private_media_root"]).resolve()
        if not media.is_dir() or not private.is_dir():
            raise CommandError("Faltan directorios temporales de medios.")
        from apps.cms.media import all_usage
        from apps.cms.models import (
            BrandPublication,
            HomePublication,
            MediaAsset,
            MenuPublication,
            PageRevision,
        )
        from apps.orders.models import Order

        checked = set()

        def check_file(value):
            for token in value.split(", "):
                path = unquote(urlsplit(token.split(" ")[0]).path)
                if path.startswith("/media/"):
                    path = path[7:]
                if path.startswith("cms/"):
                    target = (media / path).resolve()
                    if not target.is_relative_to(media) or not target.is_file():
                        raise CommandError(f"Falta archivo de biblioteca: {path}")
                    checked.add(path)

        assets: dict[int, MediaAsset] = {}

        def walk(value):
            if isinstance(value, dict):
                if {"asset", "version", "crop"} <= value.keys():
                    asset = assets.get(value["asset"])
                    if not asset or value["crop"] not in asset.versions.get(
                        str(value["version"]), {}
                    ):
                        raise CommandError("Referencia de biblioteca sin generación conservada.")
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
            elif isinstance(value, str):
                check_file(value)

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
            executor = MigrationExecutor(connection)
            if executor.migration_plan(executor.loader.graph.leaf_nodes()):
                raise CommandError(
                    "La copia tiene migraciones pendientes; usa el código de su fecha."
                )
            counts = {
                m._meta.label: m.objects.count()
                for m in (
                    HomePublication,
                    PageRevision,
                    MenuPublication,
                    BrandPublication,
                    MediaAsset,
                    Order,
                )
            }
            assets = {a.pk: a for a in MediaAsset.objects.all()}
            for asset in assets.values():
                check_file(asset.original.name)
                walk(asset.versions)
            for _, _, source in all_usage():
                walk(source)
            # Verify every FileField too, including private payment supports and catalog files.
            from django.apps import apps
            from django.db.models import FileField

            for model in apps.get_models():
                for field in model._meta.fields:
                    if not isinstance(field, FileField):
                        continue
                    root = (
                        private
                        if Path(cast(Any, field.storage).location).resolve()
                        == Path(settings.PRIVATE_MEDIA_ROOT).resolve()
                        else media
                    )
                    for path in model._default_manager.exclude(**{field.name: ""}).values_list(
                        field.name, flat=True
                    ):
                        if not path:
                            continue
                        target = (root / path).resolve()
                        if not target.is_relative_to(root) or not target.is_file():
                            raise CommandError(f"Falta archivo: {model._meta.label}.{field.name}")
            self.stdout.write(
                json.dumps({"recuentos": counts, "archivos_cms": len(checked)}, ensure_ascii=False)
            )
            self.stdout.write("Verificación correcta; base real intacta.")
