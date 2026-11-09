import hashlib
import inspect
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import RequestFactory, override_settings

from apps.orders.api import OrderDetailView
from apps.orders.dev_middleware import TrackingReadsMiddleware


def test_vista_sin_instrumentacion_y_settings_sin_middleware():
    source = inspect.getsource(OrderDetailView.get)
    assert "cache" not in source and "hashlib" not in source and "DEBUG" not in source
    assert "apps.orders.dev_middleware.TrackingReadsMiddleware" not in settings.MIDDLEWARE
    from config.settings import base, dev

    middleware = "apps.orders.dev_middleware.TrackingReadsMiddleware"
    assert middleware in dev.MIDDLEWARE
    assert middleware not in base.MIDDLEWARE
    for module in ("prod.py", "test.py"):
        assert "dev_middleware" not in Path(base.__file__).with_name(module).read_text()


@pytest.mark.parametrize(
    ("method", "path", "armed", "expected"),
    [
        ("get", "/api/v1/orders/secreto", True, 1),
        ("get", "/api/v1/orders/secreto", False, None),
        ("post", "/api/v1/orders/secreto", True, 0),
        ("get", "/api/v1/orders/secreto/extra", True, 0),
    ],
)
def test_middleware_solo_cuenta_get_armados(method, path, armed, expected):
    key = "e2e:tracking:" + hashlib.sha256(b"secreto").hexdigest()
    cache.delete(key)
    if armed:
        cache.set(key, 0, 300)
    response = Mock()
    middleware = TrackingReadsMiddleware(lambda request: response)
    assert middleware(getattr(RequestFactory(), method)(path)) is response
    assert cache.get(key) == expected
    cache.delete(key)


@pytest.mark.parametrize("debug", [False, True])
def test_vista_no_usa_cache_de_seguimiento(debug):
    with (
        override_settings(DEBUG=debug),
        patch("apps.orders.api.order_detail", return_value={}),
        patch("django.core.cache.cache.get", side_effect=AssertionError("No consultar caché")),
    ):
        OrderDetailView().get(Mock(), "secreto")
