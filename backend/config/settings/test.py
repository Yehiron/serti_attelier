from .base import *  # noqa: F403

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Keep Axes active: authentication tests use HTTP login requests (or force_login),
# because Axes requires authenticate(request=...) rather than Client.login().

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
PUBLIC_READ_RATE = "100000/min"

COUPON_EMAIL_PEPPER = "test-coupon-pepper"

# Deterministic payments: tests never inherit Wompi values from a developer's .env.
# Credenciales ficticias completas; los tests de indisponibilidad usan override_settings.
WOMPI_PUBLIC_KEY = "pub_test_fake"
WOMPI_PRIVATE_KEY = "prv_test_fake"
WOMPI_INTEGRITY_SECRET = "test_integrity_fake"  # noqa: S105
WOMPI_EVENTS_SECRET = "test_events_fake"  # noqa: S105

WHATSAPP_PROVIDER = "log"
SERTI_ORDERS_EMAIL = ""
WHATSAPP_ORDERS_RECIPIENT = ""

WOMPI_API_URL = "https://sandbox.wompi.co/v1"
