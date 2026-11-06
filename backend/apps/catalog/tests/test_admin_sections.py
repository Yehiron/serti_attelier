from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from django.contrib.admin.utils import flatten_fieldsets
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.urls import reverse

from apps.accounts.roles import CONTENIDO, OPERACIONES, PROPIETARIO
from apps.catalog import services
from apps.catalog.forms import PieceForm
from apps.catalog.models import Piece
from apps.core.tests.test_dashboard_client import staff

pytestmark = pytest.mark.django_db
TITLES = [
    "Información",
    "Clasificación",
    "Detalles de la pieza",
    "Precio y disponibilidad",
    "Inglés (opcional)",
    "Buscadores (SEO)",
    "Avanzado",
]


@pytest.mark.parametrize("role", [PROPIETARIO, OPERACIONES, CONTENIDO])
def test_sections_and_widgets(role: str) -> None:
    browser, _ = staff(role)
    piece = Piece.objects.create(
        sku="TABS",
        name_es="Anillo",
        slug_es="anillo",
        price_cents=125000000,
        sale_price_cents=100000000,
    )
    response = browser.get(reverse("admin:catalog_piece_change", args=[piece.pk]))
    assert response.status_code == 200
    adminform = response.context["adminform"]
    assert [str(title) for title, _ in adminform.fieldsets] == TITLES
    fields = flatten_fieldsets(adminform.fieldsets)
    assert len(fields) == len(set(fields))
    assert set(fields) == set(adminform.form.fields) | (
        set(adminform.readonly_fields) - {"price_cents", "sale_price_cents"}
    )
    expected = set(PieceForm().fields) - {
        "name",
        "slug",
        "short_description",
        "long_description",
        "story",
        "care",
        "seo_title",
        "seo_description",
    }
    if role == CONTENIDO:
        expected -= {"price_cents", "sale_price_cents"}
    assert set(adminform.form.fields) == expected
    html = response.content.decode()
    for name in adminform.form.fields:
        assert html.count(f'name="{name}"') == 1, name
    # One level of tabs: fieldsets are stacked sections inside «General».
    assert "activeFieldsetTab:" not in html
    assert all(title in html for title in TITLES)
    options = dict(adminform.fieldsets)
    assert "sku" in options["Información"]["fields"]
    assert options["Buscadores (SEO)"]["classes"] == ["collapse"]
    assert options["Avanzado"]["classes"] == ["collapse"]
    inlines = response.context["inline_admin_formsets"]
    assert [str(i.opts.verbose_name_plural) for i in inlines] == ["Fotos", "Video", "Colecciones"]
    assert all(not i.opts.tab for i in inlines)
    assert str(inlines[0].formset.empty_form.fields["original"].label) == "Foto"
    for name in ("stones", "materials", "related"):
        widget = adminform.form.fields[name].widget
        assert isinstance(getattr(widget, "widget", widget), FilteredSelectMultiple)
    assert "Dirección en la web" in html
    assert "Opcional. Cómo aparece la pieza en Google." in html
    if role == CONTENIDO:
        assert dict(adminform.fieldsets)["Precio y disponibilidad"]["fields"] == [
            "regular_price_cop",
            "sale_price_cop",
            "status",
            "sale_state",
        ]
        section = html.split("Precio y disponibilidad", 1)[1]
        section = section.split("Buscadores (SEO)", 1)[0]
        assert "$1.250.000" in section and "$1.000.000" in section
        assert 'name="price_cents"' not in html


def add_data(page: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "sku": "NEW-TABS",
        "name_es": "Anillo",
        "name_en": "Ring",
        "slug_es": "nuevo",
        "slug_en": "new",
        "price_cents": "1250000.25",
        "position": "0",
    }
    for inline in page.context["inline_admin_formsets"]:
        formset = inline.formset
        for key, value in formset.management_form.initial.items():
            data[f"{formset.prefix}-{key}"] = value
    return data


def test_add_piece_uses_service() -> None:
    browser, _ = staff(PROPIETARIO)
    url = reverse("admin:catalog_piece_add")
    page = browser.get(url)
    assert page.status_code == 200
    assert page.context["adminform"].prepopulated_fields
    with patch("apps.catalog.admin.services.save_piece", wraps=services.save_piece) as saved:
        response = browser.post(url, add_data(page))
    assert response.status_code == 302
    saved.assert_called_once()
    assert Piece.objects.get(sku="NEW-TABS").price_cents == 125000025


@pytest.mark.parametrize(
    ("field", "title"),
    [("name_es", "Información"), ("price_cents", "Precio y disponibilidad")],
)
def test_add_errors_are_visible_in_their_section(field: str, title: str) -> None:
    browser, _ = staff(PROPIETARIO)
    url = reverse("admin:catalog_piece_add")
    data = add_data(browser.get(url))
    data.pop(field)
    response = browser.post(url, data)
    assert response.status_code == 200
    assert field in response.context["adminform"].form.errors
    fieldset = next(f for f in response.context["adminform"] if str(f.name) == title)
    # A collapsed section opens by itself when one of its fields has an error.
    assert not fieldset.is_collapsible


def test_admin_passes_system_checks() -> None:
    # runserver refuses to start on admin check errors that rendering tests do not hit.
    from django.core.management import call_command

    call_command("check", fail_level="ERROR")
