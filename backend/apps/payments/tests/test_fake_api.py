"""Contrato del servidor stdlib sin abrir sockets ni consultar servicios externos."""

import importlib.util
import json
from io import BytesIO, StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.payments.wompi import WompiTransaction, event_checksum


@pytest.fixture
def fake():
    path = Path(__file__).resolve().parents[4] / "infra/wompi-fake/server.py"
    spec = importlib.util.spec_from_file_location("local_wompi_fake", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def handle(fake, method, path, body=None):
    handler = object.__new__(fake.Handler)
    encoded = json.dumps(body).encode() if body is not None else b""
    handler.path = path
    handler.rfile = BytesIO(encoded)
    handler.headers = {"Content-Length": str(len(encoded))}
    results = []
    handler.reply = lambda status, data: results.append((status, data))
    getattr(handler, "do_" + method)()
    return results[0]


@pytest.mark.parametrize("status", ["PENDING", "APPROVED", "DECLINED", "VOIDED", "ERROR"])
def test_fake_canonical_contract_and_lookup(fake, status):
    tx = {
        "id": "dev-1",
        "reference": "SRT-000001-01",
        "status": status,
        "amount_in_cents": 10000,
        "currency": "COP",
        "payment_method_type": "PSE",
    }
    assert handle(fake, "POST", "/control", {"transaction": tx}) == (200, {})
    result = handle(fake, "GET", "/v1/transactions/dev-1")
    assert result == (200, {"data": tx})
    assert WompiTransaction.parse(result[1]["data"]).status == status
    assert handle(fake, "GET", "/v1/transactions?reference=SRT-000001-01") == (200, {"data": [tx]})
    assert handle(fake, "GET", "/v1/transactions?reference=unknown") == (200, {"data": []})
    assert handle(fake, "GET", "/v1/transactions/unknown")[0] == 404
    assert handle(fake, "POST", "/control", {"unavailable": True})[0] == 200
    assert handle(fake, "GET", "/v1/transactions/dev-1")[0] == 503
    handle(fake, "POST", "/control", {"unavailable": False})
    assert handle(fake, "GET", "/v1/transactions/dev-1")[0] == 200


def test_fake_emits_signed_event_to_fixed_backend(fake, monkeypatch, settings):
    settings.WOMPI_EVENTS_SECRET = "test_events_e2e_secret"
    monkeypatch.setenv("WOMPI_EVENTS_SECRET", settings.WOMPI_EVENTS_SECRET)
    captured = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def transport(request, timeout):
        captured.append(request)
        return Response()

    monkeypatch.setattr(fake, "urlopen", transport)
    tx = {
        "id": "dev-1",
        "reference": "SRT-000001-01",
        "status": "APPROVED",
        "amount_in_cents": 10000,
        "currency": "COP",
    }
    assert handle(
        fake,
        "POST",
        "/control",
        {"transaction": tx, "emit": True, "url": "http://arbitrary.invalid"},
    ) == (200, {"webhook_status": 200})
    assert captured[0].full_url == "http://backend:8000/api/v1/payments/wompi/events"
    body = json.loads(captured[0].data)
    assert body["signature"]["checksum"] == event_checksum(body)
    assert fake.transactions["dev-1"] == body["data"]["transaction"]


def test_simulator_refuses_official_api_even_in_debug():
    with (
        override_settings(
            DEBUG=True, WOMPI_ALLOW_FAKE_API=True, WOMPI_API_URL="https://sandbox.wompi.co/v1"
        ),
        pytest.raises(CommandError, match="WOMPI_ALLOW_FAKE_API"),
    ):
        call_command(
            "simulate_wompi_event", reference="unused", status="APPROVED", stdout=StringIO()
        )
