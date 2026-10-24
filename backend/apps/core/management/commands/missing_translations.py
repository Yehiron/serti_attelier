from typing import Any

from django.core.management.base import BaseCommand
from django.db.models import QuerySet

from apps.catalog.models import Category, Collection, Material, Piece, Stone


class Command(BaseCommand):
    help = "Lista traducciones inglesas obligatorias ausentes en contenido publicado."

    def handle(self, *args: Any, **options: Any) -> None:
        missing = False
        for model in (Piece, Category, Collection, Stone, Material):
            qs: QuerySet[Any] = model.objects.all()
            if model is Piece:
                qs = qs.filter(status="published")
            elif model in (Category, Collection):
                qs = qs.filter(is_active=True)
            fields = ("name", "slug", "short_description") if model is Piece else ("name", "slug")
            for obj in qs:
                absent = [f"{field}_en" for field in fields if not getattr(obj, f"{field}_en", "")]
                if absent:
                    missing = True
                    self.stdout.write(f"{model._meta.label}:{obj.pk}: {', '.join(absent)}")
        if missing:
            raise SystemExit(1)
