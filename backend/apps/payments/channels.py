"""Payment adapters keep provider checkout details outside the order domain (ADR-008)."""

from __future__ import annotations

from typing import Any, Protocol

from apps.orders.models import Order


class PaymentChannel(Protocol):
    def checkout(
        self, order: Order, *, include_customer: bool = False
    ) -> dict[str, Any] | None: ...


class WompiChannel:
    def checkout(self, order: Order, *, include_customer: bool = False) -> dict[str, Any] | None:
        from .services import checkout_data

        return checkout_data(order, include_customer=include_customer)


class ManualChannel:
    def checkout(self, order: Order, *, include_customer: bool = False) -> None:
        return None


def channel_for(order: Order) -> PaymentChannel:
    return WompiChannel() if order.payment_channel == "wompi" else ManualChannel()
