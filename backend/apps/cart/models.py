from __future__ import annotations

import uuid

from django.db import models


class Cart(models.Model):
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    locale = models.CharField(max_length=2, default="es")
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return str(self.token)


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    piece = models.ForeignKey("catalog.Piece", on_delete=models.PROTECT)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["added_at", "pk"]
        constraints = [models.UniqueConstraint(fields=["cart", "piece"], name="cart_unique_piece")]

    def __str__(self) -> str:
        return f"{self.cart_id}: {self.piece_id}"
