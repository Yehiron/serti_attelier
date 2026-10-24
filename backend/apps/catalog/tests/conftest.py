from __future__ import annotations

from collections.abc import Callable, Iterator
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from django.core.files.base import ContentFile
from django.test import override_settings
from PIL import Image

from apps.catalog.models import Category, Piece, PieceImage
from apps.catalog.services import publish_piece, save_piece_image


@pytest.fixture(autouse=True)
def media(tmp_path: Path) -> Iterator[None]:
    with override_settings(MEDIA_ROOT=tmp_path):
        yield


def image_file(
    fmt: str = "PNG", size: tuple[int, int] = (960, 1200), **kwargs: Any
) -> ContentFile[bytes]:
    output = BytesIO()
    Image.new("RGB", size, "#591e24").save(output, format=fmt, **kwargs)
    return ContentFile(output.getvalue(), name=f"test.{fmt.lower()}")


@pytest.fixture
def make_piece(django_capture_on_commit_callbacks: Any) -> Callable[..., Piece]:
    def create(*, published: bool = True, **kwargs: Any) -> Piece:
        number = Piece.objects.count() + 1
        category, _ = Category.objects.get_or_create(
            slug_es="anillos",
            defaults={"name_es": "Anillos", "name_en": "Rings", "slug_en": "rings"},
        )
        defaults: dict[str, Any] = {
            "sku": f"TEST-{number}",
            "name_es": f"Pieza {number}",
            "name_en": f"Piece {number}",
            "slug_es": f"pieza-{number}",
            "slug_en": f"piece-{number}",
            "short_description_es": "Pieza única",
            "short_description_en": "Unique piece",
            "price_cents": 100_000,
            "category": category,
        }
        defaults.update(kwargs)
        piece = Piece.objects.create(**defaults)
        if published:
            with django_capture_on_commit_callbacks(execute=True):
                save_piece_image(
                    PieceImage(
                        piece=piece, original=image_file(), alt_es="Una joya", is_primary=True
                    )
                )
            piece = publish_piece(piece, None)
        return piece

    return create
