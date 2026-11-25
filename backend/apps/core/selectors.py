from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote, urlencode

from django.conf import settings
from django.db import transaction
from django.utils.translation import override

from .models import SiteSettings
from .whatsapp import render_whatsapp

if TYPE_CHECKING:
    from apps.catalog.models import Piece


@transaction.atomic
def get_solo() -> SiteSettings:
    with override("es"):
        obj, created = SiteSettings.objects.get_or_create(pk=1)
    if created:
        defaults = {
            "general": "Hello SERTI, I would like information about {name} ({sku}). {url}",
            "preorder": "Hello SERTI, I am interested in preordering {name} ({sku}). {url}",
            "reserved": (
                "Hello SERTI, please let me know if {name} ({sku}) becomes available. {url}"
            ),
            "sold": (
                "Hello SERTI, I fell in love with {name} ({sku}) "
                "and would like a unique piece inspired by it. {url}"
            ),
        }
        for kind, text in defaults.items():
            setattr(obj, f"whatsapp_{kind}_en", text)
        obj.manual_payment_instructions_en = (
            "SERTI will share Efecty or transfer details via WhatsApp. "
            "Order {number}, total {total}. Pay before {deadline}."
        )
        obj.save()
    return obj


def piece_url(piece: Piece, locale: str) -> str:
    with override(locale):
        segment = "pieces" if locale == "en" else "piezas"
        return f"{settings.PUBLIC_SITE_URL}/{locale}/{segment}/{quote(piece.slug)}"


def whatsapp_url(
    kind: str, piece: Piece, locale: str, config: SiteSettings | None = None
) -> str | None:
    config = config or get_solo()
    if not config.whatsapp_number:
        return None
    if kind not in {"general", "preorder", "reserved", "sold"}:
        raise ValueError("Unknown WhatsApp template")
    with override(locale):
        text = render_whatsapp(
            getattr(config, f"whatsapp_{kind}"),
            name=piece.name,
            sku=piece.sku,
            url=piece_url(piece, locale),
        )
    return f"https://wa.me/{config.whatsapp_number}?{urlencode({'text': text})}"
