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
    assert response.json() == {"status": "ok", "checks": {"database": True, "redis": True}}


@pytest.mark.django_db
def test_ready_returns_503_when_a_dependency_fails(
    client: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("apps.core.health.check_redis", lambda: False)
    response = client.get(reverse("health-ready"))
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": True, "redis": False}
