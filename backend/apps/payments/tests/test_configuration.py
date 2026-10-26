from __future__ import annotations

import runpy
from typing import Any

import pytest
from django.core.exceptions import ImproperlyConfigured

from config.settings import base


@pytest.mark.parametrize(
    "key,api",
    [
        ("pub_test_x", "https://production.wompi.co/v1"),
        ("pub_prod_x", "https://sandbox.wompi.co/v1"),
    ],
)
def test_production_key_mismatch(monkeypatch: Any, key: str, api: str) -> None:
    monkeypatch.setattr(base, "WOMPI_PUBLIC_KEY", key)
    monkeypatch.setattr(base, "WOMPI_API_URL", api)
    monkeypatch.setattr(base, "COUPON_EMAIL_PEPPER", "test")
    with pytest.raises(ImproperlyConfigured, match="Wompi public key"):
        runpy.run_module("config.settings.prod")


@pytest.mark.parametrize(
    "key,api",
    [
        ("", "https://sandbox.wompi.co/v1"),
        ("pub_test_x", "https://sandbox.wompi.co/v1"),
        ("pub_prod_x", "https://production.wompi.co/v1"),
    ],
)
def test_production_valid_configuration(monkeypatch: Any, key: str, api: str) -> None:
    monkeypatch.setattr(base, "WOMPI_PUBLIC_KEY", key)
    monkeypatch.setattr(base, "WOMPI_API_URL", api)
    monkeypatch.setattr(base, "COUPON_EMAIL_PEPPER", "test")
    assert runpy.run_module("config.settings.prod")["DEBUG"] is False


def test_dev_event_secret_default(monkeypatch: Any) -> None:
    monkeypatch.delenv("WOMPI_EVENTS_SECRET", raising=False)
    assert runpy.run_module("config.settings.dev")["WOMPI_EVENTS_SECRET"] == "test_events_dev_only"
