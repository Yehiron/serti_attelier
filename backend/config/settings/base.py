"""Settings shared by every environment.

All secrets and host-specific values come from environment variables
(documented in the repository's .env.example). Nothing here may contain a
real secret.
"""

from pathlib import Path
from typing import Any

import environ

BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env()

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# Path of the admin dashboard, e.g. "dashboard-x7k2/". Kept configurable so the
# public site does not expose a predictable /admin/ (see docs/security-plan.md).
ADMIN_URL = env("DJANGO_ADMIN_URL", default="dashboard/")
API_SCHEMA_PUBLIC = env.bool("API_SCHEMA_PUBLIC", default=False)

INSTALLED_APPS = [
    "modeltranslation",
    "unfold",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "drf_spectacular",
    "apps.core",
    "django_otp",
    "config.admin_apps.SpanishTOTPConfig",
    "config.admin_apps.SpanishAxesConfig",
    "apps.accounts",
    "apps.audit",
    "apps.catalog",
    "apps.inventory",
    "apps.cms",
    "apps.cart",
    "apps.pricing",
    "apps.promotions",
    "apps.orders",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "apps.accounts.middleware.AdminAccessMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

REDIS_URL = env("REDIS_URL")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOCALE_PATHS = [BASE_DIR / "locale"]
LANGUAGE_CODE = "es"
LANGUAGES = [("es", "Español"), ("en", "English")]
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = env.path("DJANGO_MEDIA_ROOT", default=BASE_DIR / "media")

# Secure by default: every API view must opt in to public access explicitly.
REST_FRAMEWORK: dict[str, Any] = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_PERMISSION_CLASSES": ["apps.accounts.permissions.IsVerifiedStaff"],
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
}

SPECTACULAR_SETTINGS = {
    "TITLE": "SERTI API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

CELERY_BROKER_URL = REDIS_URL
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 120

LOGGING: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "filters": {"redact": {"()": "apps.core.observability.RedactionFilter"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain", "filters": ["redact"]},
    },
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", default="INFO")},
}

AUTH_USER_MODEL = "accounts.User"
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
AXES_FAILURE_LIMIT = 5
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_COOLOFF_TIME = 0.5
AXES_RESET_ON_SUCCESS = True
# Use the same one-hop parser for rate limiting and audit evidence. No ipware dependency.
AXES_CLIENT_IP_CALLABLE = "apps.core.http.client_ip"
AXES_LOCKOUT_TEMPLATE = "admin/accounts/locked_out.html"
OTP_TOTP_ISSUER = "SERTI"
OTP_ADMIN_HIDE_SENSITIVE_DATA = True
SESSION_COOKIE_AGE = 1800
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="SERTI <no-reply@serti.localhost>")
UNFOLD = {
    "DASHBOARD_CALLBACK": "apps.orders.metrics.dashboard_callback",
    "SITE_TITLE": "SERTI",
    "SITE_HEADER": "SERTI",
    "COLORS": {
        # Official palette: crimson 600, wine 800, plum 950 (docs/marca.md).
        "primary": {
            "50": "#f8f1f3",
            "100": "#f0e1e5",
            "200": "#e1c2cb",
            "300": "#ca96a5",
            "400": "#b1627a",
            "500": "#9a3654",
            "600": "#8a1538",
            "700": "#781835",
            "800": "#651c32",
            "900": "#4c1023",
            "950": "#330414",
        },
    },
}

MODELTRANSLATION_DEFAULT_LANGUAGE = "es"
MODELTRANSLATION_FALLBACK_LANGUAGES = ("es",)
PUBLIC_SITE_URL = env("PUBLIC_SITE_URL", default="https://serti.localhost").rstrip("/")
REST_FRAMEWORK.update(
    {
        "EXCEPTION_HANDLER": "apps.core.exceptions.problem_handler",
        "NUM_PROXIES": 1,
        "DEFAULT_THROTTLE_RATES": {"public_reads": "120/min"},
    }
)
CELERY_BEAT_SCHEDULE = {
    "release-expired-piece-reservations": {
        "task": "apps.inventory.tasks.release_expired_reservations",
        "schedule": 60.0,
    },
}

INTERNAL_API_TOKEN = env("INTERNAL_API_TOKEN", default="")

COUPON_EMAIL_PEPPER = env("COUPON_EMAIL_PEPPER", default="")
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].update(
    {
        # Production defaults; development can raise them (e.g. for browser tests from one IP).
        "cart_add": env("THROTTLE_CART_ADD", default="30/min"),
        "checkout_quote": env("THROTTLE_CHECKOUT_QUOTE", default="20/min"),
        "orders_minute": env("THROTTLE_ORDERS_MINUTE", default="5/min"),
        "orders_hour": env("THROTTLE_ORDERS_HOUR", default="20/hour"),
    }
)
CELERY_BEAT_SCHEDULE["cleanup-carts"] = {
    "task": "apps.cart.tasks.delete_expired_carts",
    "schedule": 86400.0,
}

SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"] = {"PaymentChannelEnum": ["wompi", "manual"]}

INSTALLED_APPS.append("apps.payments")
PRIVATE_MEDIA_ROOT = env.path("DJANGO_PRIVATE_MEDIA_ROOT", default=BASE_DIR / "private_media")
WOMPI_PUBLIC_KEY = env("WOMPI_PUBLIC_KEY", default="")
WOMPI_PRIVATE_KEY = env("WOMPI_PRIVATE_KEY", default="")
WOMPI_INTEGRITY_SECRET = env("WOMPI_INTEGRITY_SECRET", default="")
WOMPI_EVENTS_SECRET = env("WOMPI_EVENTS_SECRET", default="")
WOMPI_API_URL = env("WOMPI_API_URL", default="https://sandbox.wompi.co/v1")
WOMPI_CHECKOUT_URL = env("WOMPI_CHECKOUT_URL", default="https://checkout.wompi.co/p/")
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].update(
    {"payment_sync": "10/min", "payment_attempts": "10/min"}
)
CELERY_BEAT_SCHEDULE["reconcile-payments"] = {
    "task": "apps.payments.tasks.reconcile_pending",
    "schedule": 300.0,
}

# Transactional notifications; SMTP provider remains deployment-specific (P-13).
INSTALLED_APPS.append("apps.notifications")
SERTI_ORDERS_EMAIL = env("SERTI_ORDERS_EMAIL", default="")
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=15)
WHATSAPP_PROVIDER = env("WHATSAPP_PROVIDER", default="log")
WHATSAPP_API_VERSION = env("WHATSAPP_API_VERSION", default="v26.0")
WHATSAPP_PHONE_NUMBER_ID = env("WHATSAPP_PHONE_NUMBER_ID", default="")
WHATSAPP_ACCESS_TOKEN = env("WHATSAPP_ACCESS_TOKEN", default="")
WHATSAPP_ORDERS_RECIPIENT = env("WHATSAPP_ORDERS_RECIPIENT", default="")
WHATSAPP_TEMPLATE_NEW_ORDER = env("WHATSAPP_TEMPLATE_NEW_ORDER", default="")
WHATSAPP_TEMPLATE_NEEDS_ATTENTION = env("WHATSAPP_TEMPLATE_NEEDS_ATTENTION", default="")
WHATSAPP_TEMPLATE_LANG = env("WHATSAPP_TEMPLATE_LANG", default="es")
CELERY_BEAT_SCHEDULE["retry-notifications"] = {
    "task": "apps.notifications.tasks.retry_failed",
    "schedule": 600.0,
}

THROTTLE_WOMPI_EVENTS = env("THROTTLE_WOMPI_EVENTS", default="120/min")
