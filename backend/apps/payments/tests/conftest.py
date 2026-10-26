from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Piece
from apps.orders.models import Order
from apps.orders.tests.conftest import client, payload, piece, reset_cache  # noqa: F401
from apps.orders.tests.test_checkout import add, submit


@pytest.fixture
def order(client: APIClient, piece: Piece, payload: dict[str, Any]) -> Order:  # noqa: F811
    add(client, piece)
    response = submit(client, payload)
    assert response.status_code == 201
    return Order.objects.get(public_token=response.data["public_token"])
