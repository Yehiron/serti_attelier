from .base import *  # noqa: F403

DEBUG = True
API_SCHEMA_PUBLIC = True
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="mailpit")  # noqa: F405
EMAIL_PORT = env.int("EMAIL_PORT", default=1025)  # noqa: F405

# This secret is intentionally restricted to the development settings module.
WOMPI_EVENTS_SECRET = env("WOMPI_EVENTS_SECRET", default="") or "test_events_dev_only"  # noqa: F405

# Local testing only: skip the dashboard's two-step verification unless explicitly enabled.
ADMIN_2FA_REQUIRED = env.bool("ADMIN_2FA_REQUIRED", default=False)  # noqa: F405

MIDDLEWARE = [*MIDDLEWARE, "apps.orders.dev_middleware.TrackingReadsMiddleware"]  # noqa: F405
