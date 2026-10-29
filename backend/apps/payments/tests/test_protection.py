from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import Client, override_settings

from apps.payments.models import PaymentEvent

URL = "/api/v1/payments/wompi/events"


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    cache.clear()


@pytest.mark.django_db
@override_settings(THROTTLE_WOMPI_EVENTS="2/min")
def test_rate_limit_prevents_writes() -> None:
    client = Client()
    for _ in range(2):
        assert client.post(URL, data={}, content_type="application/json").status_code == 200
    with patch("apps.payments.api.record_event") as record:
        response = client.post(URL, data={}, content_type="application/json")
        assert response.status_code == 429
        assert response.json() == {}
        record.assert_not_called()
    assert PaymentEvent.objects.count() == 1


@pytest.mark.django_db
def test_invalid_storage_per_trusted_ip(caplog: pytest.LogCaptureFixture) -> None:
    client = Client()
    for index in range(4):
        client.post(
            URL,
            data={},
            content_type="application/json",
            HTTP_X_FORWARDED_FOR=f"10.0.0.{index}, 192.0.2.1",
        )
    assert PaymentEvent.objects.count() == 1
    assert "Wompi invalid checksum suppressed count=3" in caplog.text
    client.post(URL, data={}, content_type="application/json", HTTP_X_FORWARDED_FOR="192.0.2.2")
    assert PaymentEvent.objects.count() == 2


@pytest.mark.django_db
def test_valid_events_always_stored() -> None:
    client = Client()
    client.post(URL, data={}, content_type="application/json")
    with patch("apps.payments.api.verify_event", return_value=True):
        for _ in range(3):
            assert (
                client.post(
                    URL, data={"event": "other"}, content_type="application/json"
                ).status_code
                == 200
            )
    assert PaymentEvent.objects.count() == 4


@override_settings(THROTTLE_WOMPI_EVENTS="1/min")
def test_size_limit_before_rate_limit() -> None:
    client = Client()
    with patch("apps.payments.api.rate_allowed", return_value=False) as rate:
        assert (
            client.post(URL, data=b"x" * 65537, content_type="application/json").status_code == 413
        )
        rate.assert_not_called()
