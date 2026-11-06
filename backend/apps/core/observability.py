"""Shared, side-effect-free redaction for monitoring and application logs."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from sentry_sdk._types import Event

REDACTED = "[REDACTED]"
_PATTERNS = re.compile(
    r"[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}"
    r"|(?<!\w)(?:\+57(?:[\s-]*\d){10}|3(?:[\s-]*\d){9})(?!\d)"
    r"|\b(?:pub_|prv_|test_|prod_)[A-Za-z0-9_-]+"
    r"|\b[0-9a-fA-F]{32,}\b"
)
_HEADERS = {"authorization", "x-internal-token", "x-event-checksum", "cookie", "set-cookie"}
_PRIVATE = {
    "cookies",
    "query_string",
    "data",
    "password",
    "address",
    "document",
    "email",
    "phone",
    "payload",
    "public_token",
}
_HEADER_TEXT = re.compile(
    r"(?i)((?:authorization|x-internal-token|x-event-checksum|cookies?)\s*[:=]\s*)[^\r\n,;]+"
)
_QUERY = re.compile(r"(https?://[^\s?#]+|/[^\s?]*)\?[^\s#]*")


def normalize_order_path(value: str) -> str:
    return re.sub(
        r"(/api/v1/orders/|/(?:es/|en/)?(?:pedido|order)/)[^/\s?#\"']+", r"\1:token", value
    )


def redact_text(value: str) -> str:
    value = normalize_order_path(value)
    value = _HEADER_TEXT.sub(lambda match: match[1] + REDACTED, value)
    value = _QUERY.sub(lambda match: match[1] + "?" + REDACTED, value)
    return _PATTERNS.sub(REDACTED, value)


def scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: REDACTED
            if str(key).lower().replace("_", "-") in _HEADERS or str(key).lower() in _PRIVATE
            else scrub(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        # Sentry also accepts headers as a sequence of pairs.
        return [
            [item[0], REDACTED]
            if isinstance(item, (list, tuple))
            and len(item) == 2
            and str(item[0]).lower() in _HEADERS
            else scrub(item)
            for item in value
        ]
    return redact_text(value) if isinstance(value, str) else value


def before_send(event: Event, hint: dict[str, Any]) -> Event:
    return cast("Event", scrub(event))


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, (dict, list, tuple)):
            record.msg = scrub(record.msg)
        if isinstance(record.args, dict):
            record.args = scrub(record.args)
        elif record.args:
            record.args = tuple(scrub(record.args))
        record.msg = redact_text(record.getMessage())
        record.args = ()
        if record.exc_info:
            record.exc_text = redact_text(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        if record.exc_text:
            record.exc_text = redact_text(record.exc_text)
        if record.stack_info:
            record.stack_info = redact_text(record.stack_info)
        return True


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": self.formatTime(record),
                "level": record.levelname,
                "logger": record.name,
                "message": redact_text(record.getMessage()),
                "exception": redact_text(record.exc_text) if record.exc_text else None,
            },
            ensure_ascii=False,
        )
