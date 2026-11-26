from __future__ import annotations

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class Cart(models.Model):
    token = models.UUIDField(
        verbose_name=_("Identificador de acceso"), default=uuid.uuid4, unique=True, editable=False
    )
    locale = models.CharField(verbose_name=_("Idioma"), max_length=2, default="es")
    expires_at = models.DateTimeField(verbose_name=_("Vence el"))
    created_at = models.DateTimeField(verbose_name=_("Creado el"), auto_now_add=True)

    class Meta:
        verbose_name = _("carrito")
        verbose_name_plural = _("carritos")

    def __str__(self) -> str:
        return str(self.token)


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart, verbose_name=_("Carrito"), on_delete=models.CASCADE, related_name="items"
    )
    piece = models.ForeignKey("catalog.Piece", verbose_name=_("Pieza"), on_delete=models.CASCADE)
    added_at = models.DateTimeField(verbose_name=_("Añadida el"), auto_now_add=True)

    class Meta:
        verbose_name = _("pieza del carrito")
        verbose_name_plural = _("piezas del carrito")
        ordering = ["added_at", "pk"]
        constraints = [models.UniqueConstraint(fields=["cart", "piece"], name="cart_unique_piece")]

    def __str__(self) -> str:
        return f"{self.cart_id}: {self.piece_id}"
