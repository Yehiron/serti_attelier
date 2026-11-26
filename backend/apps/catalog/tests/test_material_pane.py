import importlib
import json
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.contrib.auth.models import Permission
from django.db import connection
from django.urls import reverse

from apps.accounts.roles import PROPIETARIO
from apps.catalog.api.serializers import MaterialNamedSerializer, MaterialTaxonSerializer
from apps.catalog.models import Material, Piece
from apps.core.tests.test_dashboard_client import staff

pytestmark = pytest.mark.django_db


def payload(**values):
    return {
        "name_es": "Oro rosa",
        "name_en": "Rose gold",
        "slug_es": "oro-rosa",
        "slug_en": "rose-gold",
        "position": "0",
        **values,
    }


def test_render_and_permissions():
    browser, user = staff(PROPIETARIO)
    material = Material.objects.create(name_es="Oro", slug_es="oro")
    empty = Material.objects.create(name_es="Plata", slug_es="plata")
    piece = Piece.objects.create(name_es="Anillo", slug_es="anillo", sku="MAT-1", price_cents=1000)
    piece.materials.add(material)
    url = reverse("admin:catalog_material_changelist")
    html = browser.get(url).content.decode()
    assert (
        "1 piezas" in html and "1 sin piezas" in html and "Plata" in html and "¿quilates?" in html
    )
    assert browser.get(url + "?material=new").status_code == 200
    user.groups.clear()
    user.user_permissions.add(Permission.objects.get(codename="view_material"))
    html = browser.get(url + f"?material={material.pk}").content.decode()
    assert 'class="mat-form"' not in html
    assert browser.post(url + f"?material={material.pk}", payload()).status_code == 403
    assert (
        browser.post(
            reverse("admin:catalog_material_reorder"), {"ids": json.dumps([material.pk, empty.pk])}
        ).status_code
        == 403
    )


def test_create_edit_validation_and_reorder():
    browser, _ = staff(PROPIETARIO)
    url = reverse("admin:catalog_material_changelist")
    assert browser.post(url + "?material=new", payload(color="#123456")).status_code == 302
    material = Material.objects.get(slug_es="oro-rosa")
    assert material.color == "#123456"
    assert browser.post(url + f"?material={material.pk}", payload(color="rojo")).status_code == 200
    material.refresh_from_db()
    assert material.color == "#123456"
    assert (
        browser.post(url + f"?material={material.pk}", payload(color="#abcdef")).status_code == 302
    )
    material.refresh_from_db()
    assert material.color == "#abcdef"
    other = Material.objects.create(name_es="Plata", slug_es="plata")
    reorder = reverse("admin:catalog_material_reorder")
    assert browser.post(reorder, {"ids": json.dumps([other.pk, material.pk])}).status_code == 200
    other.refresh_from_db()
    assert other.position == 0
    assert browser.post(reorder, {"ids": json.dumps([other.pk, other.pk])}).status_code == 400


def test_population_and_serializers():
    material = Material.objects.create(name_es="Oro blanco", slug_es="oro-blanco")
    silver = Material.objects.create(name_es="Plata", slug_es="plata")
    migration = importlib.import_module("apps.catalog.migrations.0015_material_color")
    migration.populate(apps, SimpleNamespace(connection=connection))
    material.refresh_from_db()
    silver.refresh_from_db()
    assert material.color == "#dcdcd8" and silver.color == "#c9ccce"
    assert MaterialNamedSerializer(material).data["color"] == "#dcdcd8"
    assert MaterialTaxonSerializer(material).data["color"] == "#dcdcd8"
