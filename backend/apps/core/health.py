"""Dependency checks used by the readiness endpoint."""

import redis
from django.conf import settings
from django.db import connection


def check_database() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            return bool(cursor.fetchone() == (1,))
    except Exception:
        return False


def check_redis() -> bool:
    try:
        client = redis.Redis.from_url(
            settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1
        )
        return bool(client.ping())
    except Exception:
        return False
