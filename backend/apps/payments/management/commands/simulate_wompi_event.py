from __future__ import annotations

import json
from argparse import ArgumentParser
from typing import Any
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.payments.configuration import fake_api_enabled
from apps.payments.models import PaymentAttempt


class Command(BaseCommand):
    help = "Fija la transacción canónica en el fake y dispara su webhook firmado (solo DEBUG)."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--reference", required=True)
        parser.add_argument(
            "--status",
            required=True,
            choices=["PENDING", "APPROVED", "DECLINED", "ERROR", "VOIDED"],
        )
        parser.add_argument("--transaction-id")
        parser.add_argument("--unavailable", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        if not fake_api_enabled(settings):
            raise CommandError("El simulador requiere DEBUG=True y WOMPI_ALLOW_FAKE_API=True.")
        attempt = PaymentAttempt.objects.filter(reference=options["reference"]).first()
        if attempt is None:
            raise CommandError("Referencia desconocida.")
        body = {
            "transaction": {
                "id": options["transaction_id"]
                or attempt.provider_transaction_id
                or f"dev-{attempt.reference}",
                "reference": attempt.reference,
                "status": options["status"],
                "amount_in_cents": attempt.amount_cents,
                "currency": attempt.currency,
                "payment_method_type": "PSE",
            },
            "emit": True,
            "unavailable": options["unavailable"],
        }
        request = Request(  # noqa: S310
            settings.WOMPI_API_URL.removesuffix("/v1") + "/control",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=20) as response:  # noqa: S310
            result = json.load(response)
        self.stdout.write(str(result["webhook_status"]))
