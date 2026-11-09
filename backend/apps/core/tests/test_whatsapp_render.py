from urllib.parse import parse_qs, urlparse

import pytest

from apps.core.whatsapp import render_whatsapp


@pytest.mark.parametrize(
    ("template", "general", "piece"),
    [
        (
            "Hola SERTI, quisiera información sobre {name} ({sku}). {url}",
            "Hola SERTI, quisiera información. https://serti.co/es",
            "Hola SERTI, quisiera información sobre Anillo (A-1). https://serti.co/es",
        ),
        (
            "Hello SERTI, I would like information about {name} ({sku}). {url}",
            "Hello SERTI, I would like information. https://serti.co/es",
            "Hello SERTI, I would like information about Anillo (A-1). https://serti.co/es",
        ),
        (
            "Consulta: {name} [{sku}], ({desconocido}).   {url}",
            "Consulta. https://serti.co/es",
            "Consulta: Anillo [A-1]. https://serti.co/es",
        ),
    ],
)
def test_render_general_y_pieza(template, general, piece):
    assert render_whatsapp(template, url="https://serti.co/es") == general
    assert render_whatsapp(template, name="Anillo", sku="A-1", url="https://serti.co/es") == piece


def test_campos_desconocidos_y_sku_vacio():
    assert render_whatsapp("{name} ({sku}) {nuevo}", name="Anillo") == "Anillo"
    assert render_whatsapp("{name.__class__} {url}", url="https://serti.co") == "https://serti.co"


@pytest.mark.django_db
@pytest.mark.parametrize("locale", ["es", "en"])
@pytest.mark.parametrize("custom", [False, True])
def test_selectores_comparten_render_sin_modificar_config(locale, custom):
    from apps.cms.selectors import site_settings
    from apps.core.selectors import get_solo, whatsapp_url

    config = get_solo()
    config.whatsapp_number = "573001234567"
    if custom:
        setattr(config, f"whatsapp_general_{locale}", "Consulta: {name} ({sku}), ({extra}). {url}")
    config.save()
    original = getattr(config, f"whatsapp_general_{locale}")
    general = parse_qs(urlparse(site_settings(locale)["whatsapp"]["general_url"]).query)["text"][0]
    assert "()" not in general and "  " not in general
    assert (
        "Consulta." if custom else ("información." if locale == "es" else "information.")
    ) in general
    from apps.catalog.models import Piece

    piece = Piece(name_es="Anillo", name_en="Ring", sku="A-1", slug_es="anillo", slug_en="ring")
    text = parse_qs(urlparse(whatsapp_url("general", piece, locale)).query)["text"][0]
    assert f"({piece.sku})" in text
    config.refresh_from_db()
    assert getattr(config, f"whatsapp_general_{locale}") == original
