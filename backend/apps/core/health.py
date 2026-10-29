"""Dependency checks used by the readiness endpoint."""

import redis
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


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


def check_migrations(*, cached: bool = True) -> bool:
    try:
        key = "health:migrations:v1"
        result = cache.get(key) if cached else None
        if isinstance(result, bool):
            return result
        executor = MigrationExecutor(connection)
        result = not executor.migration_plan(executor.loader.graph.leaf_nodes())
        if cached:
            cache.set(key, result, timeout=60)
        return result
    except Exception:
        return False
