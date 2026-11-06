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


@pytest.fixture(autouse=True)
def no_inherited_fake_flag(monkeypatch):
    monkeypatch.setattr(base, "WOMPI_ALLOW_FAKE_API", False)


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


@pytest.mark.parametrize(
    "debug,flag,url,valid",
    [
        (True, True, "http://wompi-fake:8080/v1", True),
        (False, True, "http://wompi-fake:8080/v1", False),
        (True, False, "http://wompi-fake:8080/v1", False),
        (True, True, "http://wompi-fake.evil/v1", False),
        (True, True, "http://wompi-fake@evil/v1", False),
    ],
)
def test_fake_requires_both_gates(debug, flag, url, valid, monkeypatch):
    keys = {name: prefixes[0] + "e2e_fake" for name, prefixes in KEY_PREFIXES.items()}
    with override_settings(**keys, DEBUG=debug, WOMPI_ALLOW_FAKE_API=flag, WOMPI_API_URL=url):
        assert is_configured() is valid
        if valid:
            assert wompi_configuration(None)[0].id == "payments.W002"
            for key in ("", "prv_prod_real", "prv_test_other"):
                with override_settings(WOMPI_PRIVATE_KEY=key):
                    assert not is_configured()
                    assert any(w.id == "payments.W001" for w in wompi_configuration(None))
        else:
            from apps.payments.wompi import WompiClient

            def forbidden(*args, **kwargs):
                raise AssertionError("Fake bloqueado no debe consultar transporte")

            monkeypatch.setattr("apps.payments.wompi.urlopen", forbidden)
            assert WompiClient().get_transaction("test") is None


@pytest.mark.parametrize(
    "flag,url",
    [
        (True, "https://sandbox.wompi.co/v1"),
        (False, "http://wompi-fake:8080/v1"),
    ],
)
def test_prod_rejects_fake_even_without_keys(monkeypatch, flag, url):
    monkeypatch.setattr(base, "WOMPI_ALLOW_FAKE_API", flag)
    monkeypatch.setattr(base, "WOMPI_API_URL", url)
    monkeypatch.setattr(base, "COUPON_EMAIL_PEPPER", "test")
    for name in KEY_PREFIXES:
        monkeypatch.setattr(base, name, "")
    with pytest.raises(ImproperlyConfigured, match="WOMPI_ALLOW_FAKE_API"):
        runpy.run_module("config.settings.prod")


@pytest.mark.parametrize("command", ["e2e_admin_session", "e2e_order_status"])
def test_e2e_commands_reject_production(command):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    options = (
        {"reference": "unknown", "target": "preparing"} if command == "e2e_order_status" else {}
    )
    with override_settings(DEBUG=False), pytest.raises(CommandError, match="DEBUG"):
        call_command(command, **options)
