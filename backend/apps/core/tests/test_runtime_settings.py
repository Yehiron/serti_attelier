import runpy
from unittest.mock import patch

import pytest
from django.http import HttpResponse
from django.middleware.csrf import CsrfViewMiddleware, get_token
from django.test import RequestFactory, override_settings

from config.settings import base


def test_sentry_optional_and_private(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base, "COUPON_EMAIL_PEPPER", "test")
    # base has already loaded its environment; prod reads Sentry at import time.
    with patch("sentry_sdk.init") as init:
        monkeypatch.setenv("SENTRY_DSN", "")
        runpy.run_module("config.settings.prod")
        init.assert_not_called()
        monkeypatch.setenv("SENTRY_DSN", "https://key@example.com/1")
        prod = runpy.run_module("config.settings.prod")
        assert init.call_count == 1
        kwargs = init.call_args.kwargs
        assert kwargs["send_default_pii"] is False
        assert kwargs["max_request_body_size"] == "never"
        assert len(kwargs["integrations"]) == 2
        assert callable(kwargs["before_send"])
        assert str(prod["STATIC_ROOT"]) == "/srv/static"
        assert prod["SESSION_COOKIE_PATH"] == "/"
        assert prod["SESSION_COOKIE_SECURE"] is True


def test_host_csrf_cookie_has_secure_root_path() -> None:
    with override_settings(
        CSRF_COOKIE_PATH="/", CSRF_COOKIE_SECURE=True, CSRF_COOKIE_NAME="__Host-csrftoken"
    ):
        request = RequestFactory().get("/dashboard/")
        get_token(request)
        response = CsrfViewMiddleware(lambda request: HttpResponse()).process_response(
            request, HttpResponse()
        )
        cookie = response.cookies["__Host-csrftoken"]
        assert cookie["path"] == "/"
        assert cookie["secure"] is True
        assert not cookie["domain"]


def test_gunicorn_defaults_and_proxy_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    monkeypatch.delenv("FORWARDED_ALLOW_IPS", raising=False)
    with patch("os.cpu_count", return_value=32):
        config = runpy.run_path("gunicorn.conf.py")
    assert config["workers"] == 8
    assert config["forwarded_allow_ips"] == "127.0.0.1,::1"
    assert "%(q)s" not in config["access_log_format"]
    assert "%(r)s" not in config["access_log_format"]
    monkeypatch.setenv("WEB_CONCURRENCY", "3")
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "192.0.2.10")
    config = runpy.run_path("gunicorn.conf.py")
    assert config["workers"] == 3
    assert config["forwarded_allow_ips"] == "192.0.2.10"
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "*")
    with pytest.raises(ValueError):
        runpy.run_path("gunicorn.conf.py")


@pytest.mark.django_db
def test_host_session_cookie_has_secure_root_path() -> None:
    from django.contrib.sessions.middleware import SessionMiddleware

    with override_settings(
        SESSION_COOKIE_PATH="/",
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_NAME="__Host-serti_admin",
    ):
        request = RequestFactory().get("/dashboard/")
        middleware = SessionMiddleware(lambda request: HttpResponse())
        middleware.process_request(request)
        request.session["staff"] = True
        response = middleware.process_response(request, HttpResponse())
        cookie = response.cookies["__Host-serti_admin"]
        assert cookie["path"] == "/"
        assert cookie["secure"] is True
        assert not cookie["domain"]
