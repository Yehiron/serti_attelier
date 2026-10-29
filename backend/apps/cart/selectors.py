from __future__ import annotations

from typing import Any

from django.db.models import QuerySet

from apps.catalog.api.serializers import PieceListSerializer
from apps.catalog.models import Piece
from apps.core.money import Money

from .models import Cart


def pieces(cart: Cart) -> QuerySet[Piece]:
    return (
        Piece.objects.filter(cartitem__cart=cart)
        .order_by("pk")
        .prefetch_related("images", "collections")
    )


def cart_data(cart: Cart | None, removed: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    items = []
    subtotal = 0
    for piece in pieces(cart) if cart else []:
        items.append(
            {
                "sku": piece.sku,
                "slug": piece.slug,
                "name": piece.name,
                "image": PieceListSerializer().get_image(piece),
                "hover_image": PieceListSerializer().get_hover_image(piece),
                "price": Money(piece.price_cents).as_dict(),
                "sale_price": Money(piece.sale_price_cents).as_dict()
                if piece.sale_price_cents is not None
                else None,
                "effective_price": piece.effective_price.as_dict(),
                "sale_state": piece.sale_state,
                "purchasable": piece.status == "published" and piece.sale_state == "available",
            }
        )
        subtotal += piece.effective_price.amount_cents
    return {
        "items": items,
        "removed": removed or [],
        "count": len(items),
        "subtotal": Money(subtotal).as_dict(),
    }
