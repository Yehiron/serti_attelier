"""Create a fresh, published, available piece for browser end-to-end tests (DEBUG only).

Every piece is unique, so each purchase test needs its own piece; reusing the demo
catalog would sell it out after a few runs.
"""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any
from uuid import uuid4

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError, CommandParser
from PIL import Image, ImageDraw

from apps.catalog.models import Category, Piece, PieceImage, Stone
from apps.catalog.services import publish_piece, save_piece, save_piece_image, save_piece_relations
from apps.catalog.tasks import process_piece_image


class Command(BaseCommand):
    help = "Crea una pieza única publicada para pruebas E2E (solo con DEBUG)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--price-pesos", type=int, default=1_200_000)

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError("e2e_piece solo funciona con DEBUG activo.")
        category = Category.objects.filter(is_active=True).order_by("position").first()
        stone = Stone.objects.order_by("position").first()
        if category is None or stone is None:
            raise CommandError("Ejecuta seed_catalog primero.")
        token = uuid4().hex[:8]
        name = f"Pieza E2E {token}"
        piece = Piece(
            sku=f"E2E-{token}".upper(),
            name_es=name,
            name_en=f"E2E piece {token}",
            slug_es=f"pieza-e2e-{token}",
            slug_en=f"e2e-piece-{token}",
            short_description_es="Pieza creada para pruebas automáticas.",
            short_description_en="Piece created for automated tests.",
            category=category,
            price_cents=options["price_pesos"] * 100,
        )
        save_piece(piece, actor=None)
        save_piece_relations(piece, {"stones": [stone]})
        image = Image.new("RGB", (960, 1200), "#4e7366")
        ImageDraw.Draw(image).text((40, 580), name, fill="#e9e3d0")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        photo = PieceImage(
            piece=piece,
            original=ContentFile(buffer.getvalue(), name="e2e.png"),
            alt_es=name,
            alt_en=name,
            is_primary=True,
        )
        save_piece_image(photo)
        process_piece_image(photo.pk)
        publish_piece(piece, None)
        self.stdout.write(
            json.dumps(
                {"sku": piece.sku, "slug_es": piece.slug_es, "slug_en": piece.slug_en, "name": name}
            )
        )
