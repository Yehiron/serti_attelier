from typing import Any

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.catalog.models import Piece
from apps.cms.models import Page, PageRevision
from apps.core.models import Department, Municipality


@pytest.fixture(autouse=True)
def reset_cache() -> None:
    cache.clear()


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def piece() -> Piece:
    return Piece.objects.create(
        sku="P5-A",
        name_es="Anillo",
        name_en="Ring",
        slug_es="p5-a",
        slug_en="p5-a",
        price_cents=123456,
        status="published",
    )


@pytest.fixture
def payload() -> dict[str, Any]:
    department, _ = Department.objects.get_or_create(code="05", defaults={"name": "Antioquia"})
    Municipality.objects.get_or_create(
        code="05001", defaults={"name": "Medellín", "department": department, "kind": "Municipio"}
    )
    for kind in ("terms", "privacy"):
        page, _ = Page.objects.get_or_create(
            kind=kind, defaults={"slug_es": kind, "title_es": kind}
        )
        page.status = "published"
        page.version = 3
        page.save()
        PageRevision.objects.get_or_create(page=page, version=3, defaults={"snapshot": {}})
    return {
        "contact": {"name": "Cliente", "email": "test@example.com", "phone": "3001234567"},
        "shipping": {
            "municipality_code": "05001",
            "address_line": "Calle 123",
        },
        "wants_certificate": False,
        "payment_channel": "wompi",
        "accepted_terms_version": 3,
        "accepted_privacy_version": 3,
        "locale": "es",
    }
