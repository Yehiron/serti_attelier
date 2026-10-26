from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import WOMPI_API_URL, WOMPI_PUBLIC_KEY

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

if WOMPI_PUBLIC_KEY and (
    (WOMPI_PUBLIC_KEY.startswith("pub_test_") and "production.wompi.co" in WOMPI_API_URL)
    or (WOMPI_PUBLIC_KEY.startswith("pub_prod_") and "sandbox.wompi.co" in WOMPI_API_URL)
):
    raise ImproperlyConfigured("Wompi public key does not match WOMPI_API_URL environment")
