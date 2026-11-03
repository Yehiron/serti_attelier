from __future__ import annotations

from typing import Any

import pytest
from django.contrib import admin
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, RequestFactory
from django.utils import translation

from apps.accounts.models import User
from apps.accounts.roles import CONTENIDO, OPERACIONES, PROPIETARIO
from apps.accounts.services import sync_roles
from apps.core.models import Department, Municipality, SiteSettings
from apps.core.selectors import get_solo
from apps.core.services import save_site_settings

pytestmark = pytest.mark.django_db


def test_divipola_and_endpoints(client: Client) -> None:
    assert Department.objects.count() == 33
    assert Municipality.objects.count() == 1122
    assert "BOGOT" in Municipality.objects.get(pk="11001").name.upper()
    departments = client.get("/api/v1/locations/departments")
    assert departments.status_code == 200
    assert len(departments.json()) == 33
    municipalities = client.get("/api/v1/locations/departments/11/municipalities")
    assert municipalities.status_code == 200
    assert municipalities.json()[0]["code"] == "11001"
    assert client.get("/api/v1/locations/departments/00/municipalities").status_code == 404


def test_site_settings_and_permissions() -> None:
    with translation.override("en"):
        settings = get_solo()
    with translation.override("es"):
        assert settings.whatsapp_sold.startswith("Hola SERTI")
    with translation.override("en"):
        assert settings.whatsapp_sold.startswith("Hello SERTI")
    assert get_solo().pk == settings.pk
    assert SiteSettings.objects.count() == 1
    owner = User.objects.create_user(username="owner", email="owner@example.com", is_staff=True)
    owner.groups.add(Group.objects.get(name=PROPIETARIO))
    editor = User.objects.create_user(
        username="content", email="content@example.com", is_staff=True
    )
    editor.groups.add(Group.objects.get(name=CONTENIDO))
    with pytest.raises(PermissionDenied):
        save_site_settings(settings, actor=editor)
    for number in ["+573001234567", "letters", "01234"]:
        settings.whatsapp_number = number
        with pytest.raises(ValidationError):
            save_site_settings(settings, actor=owner)
    settings.whatsapp_number = "573001234567"
    save_site_settings(settings, actor=owner)
    settings.whatsapp_general_en = "{name.__class__}"
    with pytest.raises(ValidationError):
        save_site_settings(settings, actor=owner)
    with pytest.raises(IntegrityError), transaction.atomic():
        SiteSettings.objects.bulk_create([SiteSettings(pk=2)])


def test_roles_and_read_only_locations() -> None:
    sync_roles()
    for name in (PROPIETARIO, OPERACIONES, CONTENIDO):
        user = User.objects.create_user(username=name, email=f"{name}@example.com", is_staff=True)
        user.groups.add(Group.objects.get(name=name))
        assert user.has_perm("catalog.change_piece")
        assert user.has_perm("catalog.change_piece_price") == (name != CONTENIDO)
        assert user.has_perm("core.change_sitesettings") == (name == PROPIETARIO)
        assert user.has_perm("inventory.view_piecereservation") == (name != CONTENIDO)
        request = RequestFactory().get("/")
        request.user = user
        for model in (Department, Municipality):
            model_admin: Any = admin.site._registry[model]
            assert not model_admin.has_view_permission(request)
            assert not model_admin.has_change_permission(request)
            assert not model_admin.has_delete_permission(request)
            assert not model_admin.has_add_permission(request)


def test_schema_has_public_contract(client: Client) -> None:
    from django.test import override_settings
    from drf_spectacular.generators import SchemaGenerator

    with override_settings(API_SCHEMA_PUBLIC=True):
        schema = SchemaGenerator().get_schema(request=None, public=True)  # type: ignore[no-untyped-call]  # drf-spectacular generator has no annotations.
    assert schema is not None
    for path in (
        "/api/v1/catalog/pieces",
        "/api/v1/catalog/pieces/{slug}",
        "/api/v1/catalog/pieces/status",
        "/api/v1/catalog/taxonomy",
        "/api/v1/locations/departments",
        "/api/v1/locations/departments/{code}/municipalities",
    ):
        assert path in schema["paths"]
    assert schema["components"]["schemas"]["CatalogList"]["properties"]["facets"]
