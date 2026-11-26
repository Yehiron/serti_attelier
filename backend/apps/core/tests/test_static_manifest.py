"""Production serves hashed static files; every dashboard page must resolve them."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from apps.accounts.roles import PROPIETARIO
from apps.catalog.models import Category, Piece, Stone
from apps.core.tests.test_dashboard_client import staff

pytestmark = pytest.mark.django_db

MANIFEST = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"},
}


def test_dashboard_pages_render_with_hashed_static_files(tmp_path: Path) -> None:
    root = tmp_path / "static"
    with override_settings(STORAGES=MANIFEST, STATIC_ROOT=root):
        call_command("collectstatic", interactive=False, verbosity=0)
        assert (root / "staticfiles.json").exists()
        # A missing manifest entry raises instead of falling back, as in production.
        with override_settings(DEBUG=False):
            browser, _ = staff(PROPIETARIO)
            piece = Piece.objects.create(
                sku="ST-1", name_es="Anillo", slug_es="anillo-st", price_cents=1000
            )
            category = Category.objects.create(name_es="Anillos", slug_es="anillos")
            stone = Stone.objects.create(name_es="Ópalo", slug_es="opalo-st")
            pages = [
                reverse("admin:index"),
                reverse("admin:orders_order_changelist"),
                reverse("admin:catalog_piece_changelist"),
                reverse("admin:catalog_piece_change", args=[piece.pk]),
                reverse("admin:catalog_piece_change", args=[piece.pk]) + "?_modal=1",
                reverse("admin:catalog_piece_delete", args=[piece.pk]),
                reverse("admin:catalog_stone_changelist"),
                reverse("admin:catalog_stone_changelist") + f"?stone={stone.pk}",
                reverse("admin:catalog_stone_changelist") + "?stone=new",
                reverse("admin:catalog_category_changelist"),
                reverse("admin:catalog_category_changelist") + f"?category={category.pk}",
            ]
            for url in pages:
                response = browser.get(url)
                assert response.status_code == 200, url
            html = browser.get(reverse("admin:orders_order_changelist")).content.decode()
            assert "/static/orders/order-card." in html
            assert "/static/orders/order-card.css" not in html
