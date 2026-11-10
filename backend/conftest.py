from typing import Any

import pytest
from django.db import connection


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if connection.vendor != "postgresql":
        for item in items:
            if item.get_closest_marker("postgres"):
                item.add_marker(pytest.mark.skip(reason="Requires PostgreSQL"))


@pytest.fixture(autouse=True)
def no_wompi_network(monkeypatch: Any) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Mockea WompiClient: red prohibida en pruebas")

    monkeypatch.setattr("apps.payments.wompi.urlopen", forbidden)


@pytest.fixture
def cms_actor():
    """Explicit service actor for image/validation regressions unrelated to role policy."""
    from apps.accounts.models import User

    return User.objects.create_superuser(
        username="cms-regression", email="cms-regression@example.com"
    )
