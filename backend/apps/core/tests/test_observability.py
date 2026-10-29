import json
import logging

import pytest

from apps.core.observability import JSONFormatter, RedactionFilter, before_send, redact_text


@pytest.mark.parametrize(
    "value",
    [
        "ana@example.co",
        "+573001234567",
        "+576011234567",
        "3001234567",
        "pub_test_abc",
        "prv_prod_xyz",
        "test_events_secret",
        "prod_integrity_secret",
        "abcdef0123456789" * 4,
    ],
)
def test_patterns(value: str) -> None:
    assert value not in redact_text(f"Error: {value}")


def test_event_is_scrubbed_without_mutating_input() -> None:
    event = {
        "request": {
            "url": "https://example.com/pay?token=secret",
            "cookies": "session=private",
            "query_string": "email=ana@example.co",
            "headers": {
                "Authorization": "Bearer opaque",
                "X-Internal-Token": "opaque",
                "X-Event-Checksum": "opaque",
                "Accept": "application/json",
            },
            "data": {"address": "Calle 12"},
        },
        "breadcrumbs": [{"message": "Customer ana@example.co +573001234567"}],
    }
    clean = before_send(event, {})  # type: ignore[arg-type]
    encoded = json.dumps(clean)
    for value in (
        "ana@example.co",
        "3001234567",
        "opaque",
        "session=private",
        "Calle 12",
        "token=secret",
    ):
        assert value not in encoded
    assert event["request"]["cookies"] == "session=private"  # type: ignore[index]


def test_logging_formats_args_and_exception_as_json() -> None:
    record = logging.LogRecord(
        "test", logging.ERROR, "", 0, "customer=%s /pay?token=secret", ("ana@example.co",), None
    )
    assert RedactionFilter().filter(record)
    rendered = JSONFormatter().format(record)
    assert "ana@example.co" not in rendered
    assert "token=secret" not in rendered
    assert json.loads(rendered)["level"] == "ERROR"


def test_structured_logging_args_are_scrubbed() -> None:
    record = logging.LogRecord(
        "test",
        logging.INFO,
        "",
        0,
        "request=%s",
        ({"cookies": "opaque", "Authorization": "Bearer secret", "address": "Calle 12"},),
        None,
    )
    RedactionFilter().filter(record)
    assert "opaque" not in record.getMessage()
    assert "Bearer secret" not in record.getMessage()
    assert "Calle 12" not in record.getMessage()
