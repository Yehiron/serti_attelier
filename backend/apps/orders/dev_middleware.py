"""Instrumentación E2E registrada exclusivamente en los settings de desarrollo."""

import hashlib
import re
from contextlib import suppress

from django.core.cache import cache


class TrackingReadsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        match = re.fullmatch(r"/api/v1/orders/([^/]+)", request.path_info)
        if request.method == "GET" and match:
            key = "e2e:tracking:" + hashlib.sha256(match[1].encode()).hexdigest()
            if cache.get(key) is not None:
                # Puede caducar entre ambas operaciones.
                with suppress(ValueError):
                    cache.incr(key)
        return self.get_response(request)
