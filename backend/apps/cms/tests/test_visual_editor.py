from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest
from django.contrib import admin
from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, RequestFactory
from django.urls import reverse

from apps.accounts.roles import CONTENIDO, PROPIETARIO
from apps.catalog import services as catalog_services
from apps.catalog.models import Category
from apps.cms import editor_services, services
from apps.cms.admin import HomeSectionAdmin
from apps.cms.models import HeroSlide, HomeSection
from apps.cms.tests.helpers import cms_form_data, cms_version
from apps.cms.tests.test_hero_slides import upload
from apps.core.dashboard import NAVIGATION
from apps.core.tests.test_dashboard_client import staff

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media(settings: Any, tmp_path: Any) -> None:
    settings.MEDIA_ROOT = tmp_path


def endpoint(action: str) -> str:
    return reverse("visual-editor-action", args=[action])


@pytest.mark.parametrize("role", [PROPIETARIO, CONTENIDO])
@pytest.mark.parametrize("tab", ["", "taxonomy"])
def test_view(role: str, tab: str) -> None:
    browser, user = staff(role)
    response = browser.get(reverse("visual-editor"), {"tab": tab, "device": "mobile"})
    assert response.status_code == 200
    assert "Editor de la página web" in response.content.decode()
    assert 'title="Vista previa de la tienda"' in response.content.decode()
    entry = next(group for group in NAVIGATION if str(group.get("title")) == "Página web")["items"][
        0
    ]
    request = RequestFactory().get("/")
    request.user = user
    assert str(entry["title"]) == "Editor visual"
    assert entry["permission"](request)


def test_permissions() -> None:
    browser, user = staff(CONTENIDO)
    user.groups.clear()
    assert browser.get(reverse("visual-editor")).status_code == 403
    assert browser.post(endpoint("section-visibility")).status_code == 403
    entry = next(group for group in NAVIGATION if str(group.get("title")) == "Página web")["items"][
        0
    ]
    request = RequestFactory().get("/")
    request.user = user
    assert not entry["permission"](request)


def test_hero_actions() -> None:
    browser, _user = staff(CONTENIDO)
    hero = HomeSection.objects.create(kind="hero")
    existing = HeroSlide.objects.create(
        section=hero, device="mobile", position=9, image="old.webp", alt_es="Foto", alt_en="Foto"
    )
    with patch.object(services, "save_hero_slide", wraps=services.save_hero_slide) as save:
        response = browser.post(
            endpoint("hero-upload"),
            cms_form_data(
                endpoint("hero-upload"),
                {
                    "section": hero.pk,
                    "device": "mobile",
                    "files[]": [upload((90, 120)), upload((120, 90))],
                },
            ),
        )
    assert response.status_code == 200
    assert save.call_count == 2
    assert response.json()["warnings"]
    rows = list(hero.slides.filter(device="mobile"))
    assert [row.position for row in rows] == [9, 10, 11]
    assert rows[1].alt_es == "Portada SERTI 11"
    ids = [row.pk for row in reversed(rows)]
    assert (
        browser.post(
            endpoint("hero-reorder"),
            cms_form_data(
                endpoint("hero-reorder"),
                {"section": hero.pk, "device": "mobile", "ids": json.dumps(ids)},
            ),
        ).status_code
        == 200
    )
    assert list(hero.slides.filter(device="mobile").values_list("pk", flat=True)) == ids
    assert (
        browser.post(
            endpoint("hero-delete"),
            cms_form_data(
                endpoint("hero-delete"),
                {"section": hero.pk, "device": "desktop", "id": existing.pk},
            ),
        ).status_code
        == 400
    )
    assert (
        browser.post(
            endpoint("hero-delete"),
            cms_form_data(
                endpoint("hero-delete"), {"section": hero.pk, "device": "mobile", "id": existing.pk}
            ),
        ).status_code
        == 200
    )
    assert not HeroSlide.objects.filter(pk=existing.pk).exists()


@pytest.mark.parametrize("device", ["desktop", "mobile"])
def test_hero_scope_and_invalid_upload(device: str) -> None:
    browser, _user = staff(CONTENIDO)
    hero = HomeSection.objects.create(kind="hero")
    story = HomeSection.objects.create(kind="story")
    for section, selected in [(story, device), (hero, "tablet")]:
        assert (
            browser.post(
                endpoint("hero-upload"),
                cms_form_data(
                    endpoint("hero-upload"),
                    {"section": section.pk, "device": selected, "files[]": [upload((90, 120))]},
                ),
            ).status_code
            == 400
        )
    response = browser.post(
        endpoint("hero-upload"),
        cms_form_data(
            endpoint("hero-upload"),
            {
                "section": hero.pk,
                "device": device,
                "files[]": [upload((90, 120)), SimpleUploadedFile("bad.png", b"bad")],
            },
        ),
    )
    assert response.status_code == 400
    assert "imagen" in response.json()["error"]
    assert not hero.slides.exists()
    other = HomeSection.objects.create(kind="hero")
    slide = HeroSlide.objects.create(
        section=other, device=device, image="old.webp", alt_es="A", alt_en="A"
    )
    for ids in [[slide.pk], [slide.pk, slide.pk], ["1"], {}]:
        assert (
            browser.post(
                endpoint("hero-reorder"),
                cms_form_data(
                    endpoint("hero-reorder"),
                    {"section": hero.pk, "device": device, "ids": json.dumps(ids)},
                ),
            ).status_code
            == 400
        )


def test_section_services_and_publish() -> None:
    browser, owner = staff(PROPIETARIO)
    HomeSection.objects.all().delete()
    first = HomeSection.objects.create(kind="statement")
    second = HomeSection.objects.create(kind="story", position=1)
    services.publish_home(owner, expected_version=cms_version())
    request = RequestFactory().get("/")
    request.user = owner
    model_admin = HomeSectionAdmin(HomeSection, admin.site)
    assert not model_admin.publication_context(request)["pending_home_changes"]
    with patch.object(
        editor_services, "set_section_visibility", wraps=editor_services.set_section_visibility
    ) as save:
        assert (
            browser.post(
                endpoint("section-visibility"),
                cms_form_data(
                    endpoint("section-visibility"), {"section": first.pk, "visible": "false"}
                ),
            ).status_code
            == 200
        )
        save.assert_called_once()
    assert model_admin.publication_context(request)["pending_home_changes"]
    with patch.object(
        editor_services, "reorder_sections", wraps=editor_services.reorder_sections
    ) as reorder:
        assert (
            browser.post(
                endpoint("sections-reorder"),
                cms_form_data(
                    endpoint("sections-reorder"), {"ids": json.dumps([second.pk, first.pk])}
                ),
            ).status_code
            == 200
        )
        reorder.assert_called_once()
    assert list(HomeSection.objects.values_list("pk", flat=True)) == [second.pk, first.pk]
    assert (
        browser.post(
            endpoint("section-image"),
            cms_form_data(
                endpoint("section-image"), {"section": second.pk, "file": upload((100, 120))}
            ),
        ).status_code
        == 200
    )
    second.refresh_from_db()
    assert second.renditions
    assert (
        browser.post(
            endpoint("section-image"),
            cms_form_data(
                endpoint("section-image"), {"section": first.pk, "file": upload((100, 120))}
            ),
        ).status_code
        == 400
    )
    response = browser.post(
        reverse("admin:cms-home-publish"),
        cms_form_data(reverse("admin:cms-home-publish"), {"return_to": "editor"}),
    )
    assert response["Location"] == reverse("cms-review-publish", args=["home"])
    assert model_admin.publication_context(request)["pending_home_changes"]
    browser.post(response["Location"], {"expected_version": cms_version()})
    assert not model_admin.publication_context(request)["pending_home_changes"]


def test_taxonomy_cover() -> None:
    browser, _user = staff(CONTENIDO)
    category = Category.objects.create(name_es="Anillos", slug_es="anillos")
    with patch.object(
        catalog_services, "save_taxonomy", wraps=catalog_services.save_taxonomy
    ) as save:
        assert (
            browser.post(
                endpoint("taxonomy-cover"),
                cms_form_data(
                    endpoint("taxonomy-cover"),
                    {"model": "category", "id": category.pk, "file": upload((100, 120))},
                ),
            ).status_code
            == 200
        )
        save.assert_called_once()
    category.refresh_from_db()
    assert category.cover_renditions["webp"]
    response = browser.get(reverse("visual-editor"), {"tab": "taxonomy"})
    assert response.status_code == 200
    assert {"id": category.pk, "name": category.name_es} in browser.get(
        reverse("cms-editor-document")
    ).json()["choices"]["category"]
    assert (
        browser.post(
            endpoint("taxonomy-cover"),
            cms_form_data(endpoint("taxonomy-cover"), {"model": "material", "id": 1}),
        ).status_code
        == 400
    )
    group = Group.objects.get(name=CONTENIDO)
    group.permissions.remove(
        Permission.objects.get(content_type__app_label="catalog", codename="change_category")
    )
    assert (
        browser.post(
            endpoint("taxonomy-cover"),
            cms_form_data(
                endpoint("taxonomy-cover"),
                {"model": "category", "id": category.pk, "file": upload((100, 120))},
            ),
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "action",
    [
        "hero-upload",
        "hero-delete",
        "hero-reorder",
        "section-image",
        "section-visibility",
        "sections-reorder",
        "taxonomy-cover",
    ],
)
def test_post_and_csrf(action: str) -> None:
    browser, _user = staff(CONTENIDO)
    assert browser.get(endpoint(action)).status_code == 405
    secure = Client(enforce_csrf_checks=True)
    secure.cookies = browser.cookies
    assert secure.post(endpoint(action)).status_code == 403
    page = secure.get(reverse("visual-editor"))
    token = page.cookies["csrftoken"].value
    assert (
        secure.post(
            endpoint(action), {"expected_version": cms_version()}, HTTP_X_CSRFTOKEN=token
        ).status_code
        == 400
    )


def test_populated_home_uses_device_renditions_and_draft_order() -> None:
    browser, _user = staff(CONTENIDO)
    HomeSection.objects.all().delete()
    hero = HomeSection.objects.create(kind="hero", title_es="Portada visual", position=2)
    HomeSection.objects.create(
        kind="statement", title_es="Manifiesto visual", position=1, is_visible=False
    )
    for device in ("desktop", "mobile"):
        assert (
            browser.post(
                endpoint("hero-upload"),
                cms_form_data(
                    endpoint("hero-upload"),
                    {"section": hero.pk, "device": device, "files[]": [upload((100, 120))]},
                ),
            ).status_code
            == 200
        )
    for device in ("desktop", "mobile"):
        data = browser.get(reverse("cms-editor-document")).json()
        assert [row["values"]["title"]["es"] for row in data["sections"]] == [
            "Manifiesto visual",
            "Portada visual",
        ]
        assert data["sections"][0]["visible"] is False
        assert "/preview?" in data["preview"]["es"]
        own = hero.slides.get(device=device)
        other = hero.slides.exclude(device=device).get()
        assert own.renditions["webp"]
        assert (
            browser.post(
                endpoint("hero-reorder"),
                cms_form_data(
                    endpoint("hero-reorder"),
                    {"section": hero.pk, "device": device, "ids": json.dumps([other.pk])},
                ),
            ).status_code
            == 400
        )


def test_rail_renders_published_piece_rendition() -> None:
    from apps.catalog.models import Collection, CollectionPiece, Piece, PieceImage

    browser, _user = staff(CONTENIDO)
    collection = Collection.objects.create(name_es="Esmeraldas", slug_es="esmeraldas")
    HomeSection.objects.create(kind="collection_rail", collection=collection)
    piece = Piece.objects.create(
        name_es="Anillo visual",
        slug_es="anillo-visual",
        sku="VISUAL",
        status="published",
        price_cents=100,
    )
    CollectionPiece.objects.create(collection=collection, piece=piece)
    PieceImage.objects.create(
        piece=piece,
        original="original.webp",
        renditions={"webp": {"480": "pieces/small.webp"}},
        is_primary=True,
        processing_status="ready",
        alt="Anillo",
    )
    from apps.cms.selectors import draft_sections, render_sections, resolve_live

    data = browser.get(reverse("cms-editor-document")).json()
    assert {"id": piece.pk, "name": piece.name_es} in data["choices"]["piece"]
    rendered = json.dumps(resolve_live(render_sections(list(draft_sections()), "es"), "es"))
    assert "Anillo visual" in rendered
    assert "pieces/small.webp" in rendered
    assert "original.webp" not in rendered


def test_editor_titles_follow_the_site_line_rule() -> None:
    from apps.core.templatetags.client_actions import title_lines

    assert title_lines("Un poco de tierra. / Un poco de <eternidad>.") == (
        "Un poco de tierra.<br><em>Un poco de &lt;eternidad&gt;.</em>"
    )
    assert title_lines("Nuestra historia") == "Nuestra historia"
