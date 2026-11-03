from __future__ import annotations

import pytest
from django.contrib import admin
from django.contrib.admin.utils import flatten_fieldsets
from django.contrib.auth.models import Group, Permission
from django.test import Client, RequestFactory
from django.urls import reverse

from apps.accounts.roles import CONTENIDO, PROPIETARIO
from apps.cms import services
from apps.cms.admin import HomeSectionAdmin
from apps.cms.models import HeroSlide, HomePublication, HomeSection
from apps.core.tests.test_dashboard_client import staff

pytestmark = pytest.mark.django_db


def test_fields_and_owner_permissions() -> None:
    _browser, owner = staff(PROPIETARIO)
    request = RequestFactory().get("/")
    request.user = owner
    model_admin = HomeSectionAdmin(HomeSection, admin.site)
    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_delete_permission(request)
    for kind in (
        "hero",
        "statement",
        "stone_panels",
        "collection_rail",
        "story",
        "personalize",
        "banner",
    ):
        section = HomeSection(kind=kind)
        fields = flatten_fieldsets(model_admin.get_fieldsets(request, section))
        assert "kind" in model_admin.get_readonly_fields(request, section)
        assert ("subtitle_es" in fields) == (kind in {"hero", "stone_panels", "collection_rail"})
        assert ("body_es" in fields) == (kind in {"statement", "story", "personalize", "banner"})
        assert ("image" in fields) == (kind in {"story", "personalize", "banner"})
        assert ("cta_kind" in fields) == (kind in {"hero", "story", "personalize", "banner"})
        assert ("collection" in fields) == (kind == "collection_rail")
    assert model_admin.conditional_fields["cta_category"] == "cta_kind == 'category'"
    assert model_admin.conditional_fields["cta_external_url"] == "cta_kind == 'external'"
    form = model_admin.get_form(request, HomeSection(kind="hero"))
    assert form.base_fields["cta_category"].empty_label == "Selecciona una opción"


def test_banner_and_publish_from_section() -> None:
    browser, owner = staff(PROPIETARIO)
    HomeSection.objects.all().delete()
    section = HomeSection.objects.create(kind="statement", title_es="Antes")
    services.publish_home(owner)
    url = reverse("admin:cms_homesection_change", args=[section.pk])
    assert "Tienes cambios sin publicar" not in browser.get(url).content.decode()
    data = {
        "position": 0,
        "is_visible": "on",
        "title_es": "Después",
        "title_en": "After",
        "body_es": "Texto",
        "body_en": "Text",
        "_continue": "1",
    }
    assert browser.post(url, data).status_code == 302
    section.refresh_from_db()
    assert section.title_es == "Después"
    assert "Tienes cambios sin publicar" in browser.get(url).content.decode()
    assert (
        "Tienes cambios sin publicar"
        in browser.get(reverse("admin:cms_homesection_changelist")).content.decode()
    )
    response = browser.post(reverse("admin:cms-home-publish"), {"section_id": section.pk})
    assert response.status_code == 302
    assert response["Location"] == url
    html = browser.get(url).content.decode()
    assert "Tienes cambios sin publicar" not in html
    assert "Publicado" in html
    before = HomePublication.objects.count()
    response = browser.post(url, data | {"title_es": "Publicado ahora", "_savepublish": "1"})
    assert response.status_code == 302
    assert response["Location"] == url
    assert HomePublication.objects.count() == before + 1
    assert HomePublication.objects.first().snapshot["es"][0]["title"] == "Publicado ahora"  # type: ignore[union-attr]
    assert "Tienes cambios sin publicar" not in browser.get(url).content.decode()


def test_editor_without_publish_permission() -> None:
    browser, _editor = staff(CONTENIDO)
    group = Group.objects.get(name=CONTENIDO)
    group.permissions.remove(
        Permission.objects.get(content_type__app_label="cms", codename="publish_content")
    )
    section = HomeSection.objects.create(kind="statement")
    url = reverse("admin:cms_homesection_change", args=[section.pk])
    html = browser.get(url).content.decode()
    assert "Vista previa" in html
    assert "Publicar ahora" not in html
    assert "Guardar y publicar" not in html
    assert (
        browser.post(reverse("admin:cms-home-publish"), {"section_id": section.pk}).status_code
        == 403
    )
    assert (
        browser.post(url, {"position": 0, "is_visible": "on", "_savepublish": "1"}).status_code
        == 403
    )
    assert not HomePublication.objects.exists()


def test_publish_requires_csrf() -> None:
    browser, _owner = staff(PROPIETARIO)
    protected = Client(enforce_csrf_checks=True)
    protected.cookies = browser.cookies
    assert protected.post(reverse("admin:cms-home-publish")).status_code == 403


def test_legacy_publication_restore_splits_slides() -> None:
    _browser, owner = staff(PROPIETARIO)
    section = HomeSection.objects.create(kind="hero")
    source = services.section_source(section)
    source["slides"] = [
        {
            "position": 2,
            "image": "old-desktop.webp",
            "width": 1920,
            "height": 900,
            "renditions": {},
            "image_mobile": "old-phone.webp",
            "mobile_width": 750,
            "mobile_height": 1000,
            "mobile_renditions": {"webp": {"750": "phone-750.webp"}},
            "alt": "Foto",
            "alt_es": "Foto",
            "alt_en": "Photo",
        }
    ]
    publication = HomePublication.objects.create(
        snapshot={}, draft_snapshot=[source], published_by=owner
    )
    services.restore_home(publication, owner)
    assert set(HeroSlide.objects.values_list("device", "image")) == {
        ("desktop", "old-desktop.webp"),
        ("mobile", "old-phone.webp"),
    }
    assert HeroSlide.objects.get(device="mobile").renditions == {"webp": {"750": "phone-750.webp"}}
