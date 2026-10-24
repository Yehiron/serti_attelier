import pytest
from django.db import connection


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if connection.vendor != "postgresql":
        for item in items:
            if item.get_closest_marker("postgres"):
                item.add_marker(pytest.mark.skip(reason="Requires PostgreSQL"))
