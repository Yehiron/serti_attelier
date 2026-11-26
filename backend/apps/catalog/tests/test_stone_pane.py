import pytest
from django.urls import reverse

from apps.accounts.roles import PROPIETARIO
from apps.catalog.admin import stone_test_phrase
from apps.catalog.api.serializers import StoneNamedSerializer, StoneTaxonSerializer
from apps.catalog.models import Stone
from apps.core.tests.test_dashboard_client import staff

pytestmark = pytest.mark.django_db


def test_phrase_and_serializers():
    assert stone_test_phrase("Un TEXTO largo de PRUEBA aquí") == "TEXTO largo de PRUEBA"
    assert not stone_test_phrase("Una gema singular")
    stone = Stone.objects.create(name_es="Ópalo", color="#123456")
    assert StoneNamedSerializer(stone).data["color"] == "#123456"
    assert StoneTaxonSerializer(stone).data["color"] == "#123456"


def test_panel_and_reorder():
    browser, _ = staff(PROPIETARIO)
    first = Stone.objects.create(name_es="Primera", description_es="texto de prueba")
    second = Stone.objects.create(name_es="Segunda")
    url = reverse("admin:catalog_stone_changelist")
    response = browser.get(url + f"?stone={first.pk}")
    assert response.status_code == 200
    assert "texto de prueba" in response.content.decode()
    response = browser.post(
        reverse("admin:catalog_stone_reorder"), {"ids": f"[{second.pk},{first.pk}]"}
    )
    assert response.status_code == 200
    first.refresh_from_db()
    second.refresh_from_db()
    assert (second.position, first.position) == (0, 1)


def stone_payload(**values):
    return {"name_es": "Esmeralda", "description_es": "Verde intenso", "position": "0", **values}


def test_panel_saves_gem_color_and_rejects_invalid():
    browser, _ = staff(PROPIETARIO)
    stone = Stone.objects.create(name_es="Esmeralda", slug_es="esmeralda-test")
    url = reverse("admin:catalog_stone_changelist") + f"?stone={stone.pk}"
    response = browser.post(url, stone_payload(color="#0f5a3c"))
    assert response.status_code == 302 and response.url.endswith(f"?stone={stone.pk}")
    stone.refresh_from_db()
    assert stone.color == "#0f5a3c" and stone.description_es == "Verde intenso"
    response = browser.post(url, stone_payload(color="verde"))
    assert response.status_code == 200
    stone.refresh_from_db()
    assert stone.color == "#0f5a3c"
    # Empty means «automatic» (colour derived from the name in the store).
    assert browser.post(url, stone_payload(color="")).status_code == 302
    stone.refresh_from_db()
    assert stone.color == ""


def test_panel_lists_real_pieces_and_requires_permission():
    from django.contrib.auth.models import Permission

    from apps.catalog.models import Piece

    browser, user = staff(PROPIETARIO)
    stone = Stone.objects.create(name_es="Zafiro", slug_es="zafiro-test")
    piece = Piece.objects.create(
        name_es="Anillo Azul", slug_es="anillo-azul", sku="ZF-1", price_cents=1000
    )
    piece.stones.add(stone)
    url = reverse("admin:catalog_stone_changelist") + f"?stone={stone.pk}"
    html = browser.get(url).content.decode()
    assert "Anillo Azul" in html
    assert reverse("admin:catalog_piece_change", args=[piece.pk]) in html
    user.groups.clear()
    user.user_permissions.add(Permission.objects.get(codename="view_stone"))
    assert browser.get(url).status_code == 200
    assert browser.post(url, stone_payload(color="#123456")).status_code == 403
    stone.refresh_from_db()
    assert stone.color == ""
