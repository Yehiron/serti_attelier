import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.accounts.roles import OPERACIONES, PROPIETARIO
from apps.cms import media
from apps.cms.models import MediaAsset
from apps.core.tests.test_dashboard_client import staff


def test_duplicate_groups():
    rows = [
        SimpleNamespace(pk=1, alt_es="  Anillo Ázul ", width=100, height=200, size=1000),
        SimpleNamespace(pk=2, alt_es="anillo azul", width=50, height=50, size=500),
        SimpleNamespace(pk=3, alt_es="", width=100, height=200, size=1020),
        SimpleNamespace(pk=4, alt_es="Otro", width=100, height=200, size=1100),
    ]
    groups = media.duplicate_groups(rows)
    assert groups == {1: [2, 3], 2: [1], 3: [1], 4: []}


@pytest.mark.django_db
def test_counts_filters_usage_and_versions():
    browser, _ = staff(PROPIETARIO)
    a = MediaAsset.objects.create(
        original="a.webp", width=100, height=100, size=1000, alt_es="Anillo"
    )
    b = MediaAsset.objects.create(
        original="b.webp", width=200, height=200, size=500, alt_es="ANÍLLO"
    )
    c = MediaAsset.objects.create(original="c.webp", width=300, height=300, size=500)
    archived = MediaAsset.objects.create(original="d.webp", archived=True)
    sources = media.UsageIndex([("Publicado", "Portada", {"asset": a.pk})])
    url = reverse("cms-media-api")
    with patch("apps.cms.media.all_usage", return_value=sources) as usage:
        data = browser.get(url).json()
        assert usage.call_count == 1
    assert data["counts"] == {
        "": 3,
        "used": 1,
        "unused": 2,
        "no_alt": 1,
        "duplicates": 2,
        "archived": 1,
    }
    with patch("apps.cms.media.all_usage", return_value=sources):
        assert [x["id"] for x in browser.get(url, {"filter": "no_alt"}).json()["items"]] == [c.pk]
        assert {x["id"] for x in browser.get(url, {"filter": "duplicates"}).json()["items"]} == {
            a.pk,
            b.pk,
        }
    for row in (a, b):
        detail = reverse("cms-media-detail", args=[row.pk])
        body = json.dumps({"action": "archive", "expected_version": row.version})
        assert browser.post(detail, body, content_type="application/json").status_code == 200
        assert browser.post(detail, body, content_type="application/json").status_code == 409
    archived.refresh_from_db()
    assert archived.archived


@pytest.mark.django_db
def test_no_permission():
    browser, _ = staff(OPERACIONES)
    assert browser.get(reverse("cms-media-api")).status_code == 403
