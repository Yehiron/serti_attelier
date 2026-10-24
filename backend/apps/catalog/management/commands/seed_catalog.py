from datetime import timedelta
from io import BytesIO
from typing import Any

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from PIL import Image, ImageDraw

from apps.catalog.models import (
    Category,
    Collection,
    CollectionPiece,
    Material,
    Piece,
    PieceImage,
    Stone,
)
from apps.catalog.services import (
    publish_piece,
    save_collection_piece,
    save_piece,
    save_piece_image,
    save_piece_relations,
    save_taxonomy,
)
from apps.catalog.tasks import process_piece_image
from apps.inventory.services import convert_reservation, reserve_piece, set_preorder


class Command(BaseCommand):
    help = "Crea un catálogo de demostración, solo con DEBUG activo."

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError("seed_catalog requiere DEBUG=True.")
        categories = self.taxonomy(
            Category,
            [
                ("Anillos", "Rings"),
                ("Aretes", "Earrings"),
                ("Cadenas", "Chains"),
                ("Dijes", "Pendants"),
                ("Pulseras", "Bracelets"),
            ],
        )
        stones = self.taxonomy(
            Stone, [("Diamante", "Diamond"), ("Esmeralda", "Emerald"), ("Zafiro", "Sapphire")]
        )
        # 16:9 placeholder covers so the home stone panels have backgrounds in development.
        for stone, color in zip(stones, ["#2b2f33", "#1f3d33", "#1c2846"], strict=True):
            if not stone.cover_image:
                cover = Image.new("RGB", (1600, 900), color)
                ImageDraw.Draw(cover).text((60, 820), stone.name_es, fill="#e9e3d0")
                buffer = BytesIO()
                cover.save(buffer, format="PNG")
                stone.cover_image = ContentFile(buffer.getvalue(), name="cover.png")
                save_taxonomy(stone)
        collections = self.taxonomy(
            Collection,
            [
                ("Regalos", "Gifts"),
                ("Novedades y Destacados", "New and Featured"),
                ("Sets", "Sets"),
                ("Descuentos", "Sale"),
            ],
        )
        materials = self.taxonomy(
            Material,
            [("Oro 18k", "18k Gold"), ("Plata 925", "925 Silver"), ("Oro rosa", "Rose Gold")],
        )
        colors = ["#591e24", "#4e7366", "#a9946f", "#736b51"]
        for index in range(12):
            sku = f"DEMO-{index + 1:03d}"
            if Piece.objects.filter(sku=sku).exists():
                continue
            with transaction.atomic():
                name = f"{categories[index % 5].name} {stones[index % 3].name} {index + 1}"
                piece = Piece(
                    sku=sku,
                    name_es=name,
                    name_en=f"Unique jewel {index + 1}",
                    slug_es=slugify(name),
                    slug_en=f"unique-jewel-{index + 1}",
                    short_description_es="Una pieza única creada por SERTI.",
                    short_description_en="A unique piece created by SERTI.",
                    category=categories[index % 5],
                    price_cents=(index + 1) * 50_000_000,
                    sale_price_cents=(index + 1) * 40_000_000 if index % 3 == 0 else None,
                    is_new=index % 2 == 0,
                )
                save_piece(piece, actor=None)
                save_piece_relations(
                    piece, {"stones": [stones[index % 3]], "materials": [materials[index % 3]]}
                )
                save_collection_piece(
                    CollectionPiece(collection=collections[index % 4], piece=piece, position=index)
                )
                image = Image.new("RGB", (960, 1200), colors[index % 4])
                ImageDraw.Draw(image).text((40, 580), name, fill="#e9e3d0")
                output = BytesIO()
                image.save(output, format="PNG")
                photo = PieceImage(
                    piece=piece,
                    original=ContentFile(output.getvalue(), name="placeholder.png"),
                    alt_es=name,
                    alt_en=f"Unique jewel {index + 1}",
                    is_primary=True,
                )
                save_piece_image(photo)
                # Publish synchronously even when a separate worker processes uploads.
                process_piece_image(photo.pk)
                publish_piece(piece, None)
                if index % 4 == 1:
                    set_preorder(piece, True, None)
                elif index % 4 == 2:
                    reservation = reserve_piece(
                        piece.pk,
                        kind="manual",
                        reference=sku,
                        expires_at=timezone.now() + timedelta(hours=24),
                    )
                    convert_reservation(reservation.pk, reason="manual_payment_confirmed")
        self.stdout.write(self.style.SUCCESS("Catálogo de demostración listo."))

    def taxonomy(self, model: Any, names: list[tuple[str, str]]) -> list[Any]:
        result = []
        for position, (es, en) in enumerate(names):
            obj = model.objects.filter(slug_es=slugify(es)).first()
            if obj is None:
                obj = model(
                    name_es=es,
                    name_en=en,
                    slug_es=slugify(es),
                    slug_en=slugify(en),
                    position=position,
                )
                save_taxonomy(obj)
            result.append(obj)
        return result
