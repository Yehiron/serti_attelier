"""Atomic fixed-window counters shared by all webhook workers."""

import hashlib
import logging
import time

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest
from rest_framework.throttling import SimpleRateThrottle

from apps.core.http import client_ip

logger = logging.getLogger(__name__)


def count(request: HttpRequest, scope: str, seconds: int) -> int:
    ident = hashlib.sha256((client_ip(request) or "unknown").encode()).hexdigest()
    key = f"wompi:{scope}:{ident}:{int(time.time()) // seconds}"
    if cache.add(key, 1, timeout=seconds + 1):
        return 1
    try:
        return int(cache.incr(key))
    except ValueError:
        # Expiry between add and increment: retry in the current window.
        return count(request, scope, seconds)


class WompiRate(SimpleRateThrottle):
    rate = "120/min"


def rate_allowed(request: HttpRequest) -> bool:
    limit, seconds = WompiRate().parse_rate(settings.THROTTLE_WOMPI_EVENTS)
    return count(request, "requests", seconds or 60) <= (limit or 120)


def store_invalid(request: HttpRequest) -> bool:
    total = count(request, "invalid", 60)
    if total > 1:
        logger.warning("Wompi invalid checksum suppressed count=%s", total - 1)
    return total == 1
