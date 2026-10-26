from __future__ import annotations

import json
from argparse import ArgumentParser
from typing import Any
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import RequestFactory
from django.utils import timezone

from apps.payments.api import wompi_events
from apps.payments.models import PaymentAttempt
from apps.payments.wompi import event_checksum


class Command(BaseCommand):
    help = "Simula eventos Wompi únicamente en desarrollo."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--reference", required=True)
        parser.add_argument(
            "--status", required=True, choices=["APPROVED", "DECLINED", "ERROR", "VOIDED"]
        )
        parser.add_argument("--transaction-id")
        parser.add_argument("--url", default="http://localhost:8000/api/v1/payments/wompi/events")
        parser.add_argument("--in-process", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError("El simulador requiere DEBUG=True.")
        attempt = PaymentAttempt.objects.filter(reference=options["reference"]).first()
        if attempt is None:
            raise CommandError("Referencia desconocida.")
        body: dict[str, Any] = {
            "event": "transaction.updated",
            "data": {
                "transaction": {
                    "id": options["transaction_id"]
                    or attempt.provider_transaction_id
                    or f"dev-{attempt.reference}",
                    "reference": attempt.reference,
                    "status": options["status"],
                    "amount_in_cents": attempt.amount_cents,
                    "currency": attempt.currency,
                }
            },
            "timestamp": int(timezone.now().timestamp()),
            "signature": {
                "properties": [
                    "transaction.id",
                    "transaction.status",
                    "transaction.amount_in_cents",
                ]
            },
        }
        body["signature"]["checksum"] = event_checksum(body)
        payload = json.dumps(body).encode()
        if options["in_process"]:
            response = wompi_events(
                RequestFactory().post("/", data=payload, content_type="application/json")
            )
            self.stdout.write(str(response.status_code))
        else:
            request = Request(  # noqa: S310
                options["url"], data=payload, headers={"Content-Type": "application/json"}
            )
            with urlopen(request, timeout=8) as result:  # noqa: S310
                self.stdout.write(str(result.status))
