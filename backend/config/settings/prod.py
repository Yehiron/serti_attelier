from copy import deepcopy
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

from apps.payments.configuration import KEY_PREFIXES, URLS, configuration_errors

from .base import *  # noqa: F403
from .base import LOGGING as BASE_LOGGING
from .base import PUBLIC_SITE_URL, env

DEBUG = False

# Caddy terminates TLS and forwards the original scheme.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True

X_FRAME_OPTIONS = "DENY"


if not COUPON_EMAIL_PEPPER:  # noqa: F405
    raise ImproperlyConfigured("COUPON_EMAIL_PEPPER is required in production")

if WOMPI_ALLOW_FAKE_API or WOMPI_API_URL not in URLS:  # noqa: F405
    raise ImproperlyConfigured(
        "WOMPI_ALLOW_FAKE_API y WOMPI_API_URL no permiten un fake en producción"
    )

if any(globals().get(name) for name in KEY_PREFIXES):
    _wompi_errors = configuration_errors(globals())
    if _wompi_errors:
        raise ImproperlyConfigured(" ".join(_wompi_errors))

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)

# Django's admin uses the global cookie paths; __Host- requires root paths.
SESSION_COOKIE_PATH = "/"
CSRF_COOKIE_PATH = "/"
SESSION_COOKIE_NAME = "__Host-serti_admin"
CSRF_COOKIE_NAME = "__Host-csrftoken"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
STATIC_ROOT = env.path("DJANGO_STATIC_ROOT", default="/srv/static")
# Static files get a content hash in their name (order-card.3f2a1c.css): every deploy
# ships new names, so browsers never keep using an outdated dashboard stylesheet.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"},
}
MEDIA_ROOT = env.path("DJANGO_MEDIA_ROOT", default="/srv/media")
PRIVATE_MEDIA_ROOT = env.path("DJANGO_PRIVATE_MEDIA_ROOT", default="/srv/private_media")
_public_url = urlsplit(PUBLIC_SITE_URL)
CSRF_TRUSTED_ORIGINS = env.list(
    "DJANGO_CSRF_TRUSTED_ORIGINS", default=[f"{_public_url.scheme}://{_public_url.netloc}"]
)
DATA_UPLOAD_MAX_MEMORY_SIZE = 26 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024
LOGGING = deepcopy(BASE_LOGGING)
LOGGING["formatters"]["json"] = {"()": "apps.core.observability.JSONFormatter"}
LOGGING["handlers"]["console"]["formatter"] = "json"

SENTRY_DSN = env("SENTRY_DSN", default="")
SENTRY_ENVIRONMENT = env("SENTRY_ENVIRONMENT", default="production")
SENTRY_TRACES_SAMPLE_RATE = env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0)
SENTRY_RELEASE = env("SENTRY_RELEASE", default="")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    from apps.core.observability import before_send

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=SENTRY_ENVIRONMENT,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        release=SENTRY_RELEASE or None,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        send_default_pii=False,
        max_request_body_size="never",
        before_send=before_send,
    )
