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
