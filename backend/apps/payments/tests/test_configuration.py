import runpy
from typing import Any

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from apps.payments.checks import wompi_configuration
from apps.payments.configuration import KEY_PREFIXES
from apps.payments.wompi import is_configured
from config.settings import base

COMPLETE = {name: prefixes[0] + "fake" for name, prefixes in KEY_PREFIXES.items()}
COMPLETE["WOMPI_API_URL"] = "https://sandbox.wompi.co/v1"
BAD = (
    [(name, "") for name in COMPLETE]
    + [(name, prefixes[1] + "fake") for name, prefixes in KEY_PREFIXES.items()]
    + [("WOMPI_API_URL", "https://unofficial.example/v1")]
)


@pytest.mark.parametrize("name,value", BAD)
def test_incomplete_or_mixed(name: Any, value: Any, monkeypatch: Any) -> None:
    config = {**COMPLETE, name: value}
    with override_settings(**config, DEBUG=True):
        assert not is_configured()
        assert any(name in warning.msg for warning in wompi_configuration(None))
    for key, val in config.items():
        monkeypatch.setattr(base, key, val)
    monkeypatch.setattr(base, "COUPON_EMAIL_PEPPER", "test")
    with pytest.raises(ImproperlyConfigured, match=name):
        runpy.run_module("config.settings.prod")


@pytest.mark.parametrize("mode", [0, 1, None])
def test_production_valid_configuration(monkeypatch: Any, mode: Any) -> None:
    for name, prefixes in KEY_PREFIXES.items():
        monkeypatch.setattr(base, name, "" if mode is None else prefixes[mode] + "fake")
    monkeypatch.setattr(
        base,
        "WOMPI_API_URL",
        "https://production.wompi.co/v1" if mode == 1 else COMPLETE["WOMPI_API_URL"],
    )
    monkeypatch.setattr(base, "COUPON_EMAIL_PEPPER", "test")
    assert runpy.run_module("config.settings.prod")["DEBUG"] is False


def test_dev_event_secret_default(monkeypatch: Any) -> None:
    monkeypatch.delenv("WOMPI_EVENTS_SECRET", raising=False)
    assert runpy.run_module("config.settings.dev")["WOMPI_EVENTS_SECRET"] == "test_events_dev_only"
