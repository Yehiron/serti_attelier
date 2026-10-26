from __future__ import annotations

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import UTC
from http.client import HTTPException
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from django.conf import settings

from apps.core.formatting import place_name
from apps.core.routes import href

from .models import PaymentAttempt

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(settings.WOMPI_PUBLIC_KEY and settings.WOMPI_INTEGRITY_SECRET)


def integrity_signature(
    reference: str, amount_in_cents: int, currency: str, expiration_time: str = ""
) -> str:
    return hashlib.sha256(
        f"{reference}{amount_in_cents}{currency}{expiration_time}{settings.WOMPI_INTEGRITY_SECRET}".encode()
    ).hexdigest()


def checkout_fields(attempt: PaymentAttempt, *, include_customer: bool = False) -> dict[str, str]:
    """Wompi Web Checkout fields.

    Customer/shipping prefill is optional for Wompi and contains PII, so it is only added
    for the response to the person who just submitted it (POST orders), never for the
    public order view or retries reachable with the order link alone.
    """
    order = attempt.order
    assert order.reservation_expires_at is not None  # noqa: S101
    expiration = (
        order.reservation_expires_at.astimezone(UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
    municipality = order.shipping_municipality
    fields = {
        "public-key": settings.WOMPI_PUBLIC_KEY,
        "currency": attempt.currency,
        "amount-in-cents": str(attempt.amount_cents),
        "reference": attempt.reference,
        "signature:integrity": integrity_signature(
            attempt.reference, attempt.amount_cents, attempt.currency, expiration
        ),
        "expiration-time": expiration,
        "redirect-url": settings.PUBLIC_SITE_URL + href("order", order.locale, order),
    }
    if include_customer:
        fields.update(
            {
                "customer-data:email": order.customer_email,
                "customer-data:full-name": order.customer_name,
                "customer-data:phone-number": order.customer_phone,
                "shipping-address:address-line-1": order.shipping_address_line,
                "shipping-address:country": "CO",
                "shipping-address:city": place_name(municipality.name),
                "shipping-address:region": place_name(municipality.department.name),
            }
        )
    return fields


def event_checksum(body: dict[str, Any]) -> str:
    values = []
    properties = body["signature"]["properties"]
    if not isinstance(properties, list) or not properties:
        raise ValueError("Invalid properties")
    for path in properties:
        value = body["data"]
        for key in path.split("."):
            value = value[key]
        if not isinstance(value, (str, int)) or isinstance(value, bool):
            raise ValueError("Invalid property")
        values.append(str(value))
    return hashlib.sha256(
        ("".join(values) + str(body["timestamp"]) + settings.WOMPI_EVENTS_SECRET).encode()
    ).hexdigest()


def verify_event(body: dict[str, Any]) -> bool:
    if not settings.WOMPI_EVENTS_SECRET:
        return False
    try:
        supplied = body["signature"]["checksum"]
        return isinstance(supplied, str) and hmac.compare_digest(
            event_checksum(body), supplied.lower()
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


@dataclass(frozen=True)
class WompiTransaction:
    id: str
    reference: str
    status: str
    amount_in_cents: int
    currency: str
    payment_method_type: str | None = None
    created_at: str | None = None
    finalized_at: str | None = None

    @classmethod
    def parse(cls, data: Any) -> WompiTransaction | None:
        if not isinstance(data, dict) or any(
            not isinstance(data.get(k), str) or not data[k]
            for k in ("id", "reference", "status", "currency")
        ):
            return None
        if type(data.get("amount_in_cents")) is not int or data["status"] not in {
            "PENDING",
            "APPROVED",
            "DECLINED",
            "VOIDED",
            "ERROR",
        }:
            return None
        return cls(
            data["id"],
            data["reference"],
            data["status"],
            data["amount_in_cents"],
            data["currency"],
            *(
                data.get(k) if isinstance(data.get(k), str) else None
                for k in ("payment_method_type", "created_at", "finalized_at")
            ),
        )


class WompiClient:
    def _get(self, path: str) -> Any:
        if not settings.WOMPI_PRIVATE_KEY:
            return None
        request = Request(  # noqa: S310
            settings.WOMPI_API_URL.rstrip("/") + path,
            headers={"Authorization": f"Bearer {settings.WOMPI_PRIVATE_KEY}"},
        )
        try:
            with urlopen(request, timeout=8) as response:  # noqa: S310
                if response.status != 200:
                    return None
                return json.loads(response.read(1024 * 1024)).get("data")
        except (OSError, HTTPException, ValueError, TypeError, AttributeError):
            logger.warning("Wompi transaction lookup unavailable")
            return None

    def get_transaction(self, transaction_id: str) -> WompiTransaction | None:
        return WompiTransaction.parse(self._get("/transactions/" + quote(transaction_id, safe="")))

    def find_by_reference(self, reference: str) -> WompiTransaction | None:
        data = self._get("/transactions?" + urlencode({"reference": reference}))
        candidates = data if isinstance(data, list) else [data]
        for candidate in candidates:
            tx = WompiTransaction.parse(candidate)
            if tx and tx.reference == reference:
                return tx
        return None
