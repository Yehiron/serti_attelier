from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone
from rest_framework.response import Response

from apps.catalog.models import Piece
from apps.core.exceptions import PieceNotFound
from apps.orders.exceptions import CheckoutError

from .models import Cart, CartItem

COOKIE = "serti_cart"
MAX_AGE = 30 * 24 * 60 * 60


def read_cart(request: HttpRequest) -> Cart | None:
    try:
        token = signing.loads(request.COOKIES.get(COOKIE, ""), salt="serti-cart", max_age=MAX_AGE)
        return Cart.objects.filter(token=UUID(token), expires_at__gt=timezone.now()).first()
    except (signing.BadSignature, ValueError, TypeError):
        return None


@transaction.atomic
def get_or_create_cart(request: HttpRequest) -> Cart:
    return read_cart(request) or Cart.objects.create(
        locale=request.GET.get("locale", "es")
        if request.GET.get("locale") in {"es", "en"}
        else "es",
        expires_at=timezone.now() + timedelta(days=30),
    )


def set_cookie(response: Response, cart: Cart) -> None:
    response.set_cookie(
        COOKIE,
        signing.dumps(str(cart.token), salt="serti-cart"),
        max_age=MAX_AGE,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="Lax",
    )


@transaction.atomic
def add_piece(cart: Cart, sku: str) -> None:
    Cart.objects.select_for_update().get(pk=cart.pk)
    clean_cart(cart)
    piece = Piece.objects.filter(sku=sku, status="published").first()
    if piece is None:
        raise PieceNotFound()
    if piece.sale_state in {"sold", "preorder"}:
        raise CheckoutError(f"piece_{piece.sale_state}", status=409)
    if CartItem.objects.filter(cart=cart, piece=piece).exists():
        return
    if cart.items.count() >= 20:
        raise CheckoutError("cart_full")
    CartItem.objects.create(cart=cart, piece=piece)


@transaction.atomic
def remove_piece(cart: Cart, sku: str) -> None:
    cart.items.filter(piece__sku=sku).delete()


@transaction.atomic
def clean_cart(cart: Cart) -> list[dict[str, Any]]:
    removed = []
    for item in cart.items.select_related("piece"):
        piece = item.piece
        reason = piece.sale_state if piece.sale_state in {"sold", "preorder"} else "unavailable"
        if piece.sale_state in {"sold", "preorder"} or piece.status != "published":
            removed.append({"sku": piece.sku, "name": piece.name, "reason": reason})
            item.delete()
    return removed


@transaction.atomic
def empty_cart(cart: Cart) -> None:
    cart.items.all().delete()


@transaction.atomic
def delete_expired_carts() -> int:
    count, _ = Cart.objects.filter(expires_at__lt=timezone.now() - timedelta(days=30)).delete()
    return count
