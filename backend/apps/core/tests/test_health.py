import pytest
from django.urls import reverse
from rest_framework.test import APIClient


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def test_live_is_public_and_ok(client: APIClient) -> None:
    response = client.get(reverse("health-live"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_ready_reports_dependencies(client: APIClient) -> None:
    response = client.get(reverse("health-ready"))
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": True, "redis": True, "migrations": True},
    }


@pytest.mark.django_db
def test_ready_returns_503_when_a_dependency_fails(
    client: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("apps.core.health.check_redis", lambda: False)
    response = client.get(reverse("health-ready"))
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": True, "redis": False, "migrations": True}


@pytest.mark.django_db
def test_ready_fails_with_pending_migrations(
    client: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("apps.core.health.check_redis", lambda: True)
    monkeypatch.setattr("apps.core.health.check_migrations", lambda: False)
    response = client.get(reverse("health-ready"))
    assert response.status_code == 503
    assert response.json()["checks"]["migrations"] is False


@pytest.mark.django_db
def test_migrations_cached_for_sixty_seconds() -> None:
    from unittest.mock import patch

    from django.core.cache import cache

    from apps.core.health import check_migrations

    cache.clear()
    with patch("apps.core.health.MigrationExecutor") as executor:
        executor.return_value.migration_plan.return_value = []
        assert check_migrations()
        assert check_migrations()
        assert executor.call_count == 1
    cache.clear()
