from __future__ import annotations

from io import BytesIO
from typing import Any

import pytest
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import Client, RequestFactory
from django.urls import reverse
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice
from PIL import Image

from apps.accounts.models import User
from apps.catalog.image_cleanup import file_paths
from apps.cms import selectors, services
from apps.cms.admin import HeroSlideInline, HomeSectionAdmin, MobileHeroSlideInline
from apps.cms.api.serializers import HeroSerializer
from apps.cms.models import HeroSlide, HomeSection
from apps.cms.tests.helpers import cms_form_data, cms_version

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media(settings: Any, tmp_path: Any) -> None:
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def actor() -> User:
    return User.objects.create_superuser(username="hero", email="hero@example.com", password="test")


def upload(size: tuple[int, int]) -> ContentFile[bytes]:
    output = BytesIO()
    Image.new("RGB", size, "red").save(output, "PNG")
    return ContentFile(output.getvalue(), name="upload.png")


def slide(section: HomeSection, **kwargs: Any) -> HeroSlide:
    cms_actor, _ = User.objects.get_or_create(
        username="hero-helper",
        defaults={"email": "hero-helper@example.com", "is_staff": True, "is_superuser": True},
    )
    obj = HeroSlide(section=section, alt_es="Piedra", alt_en="Stone", **kwargs)
    services.save_hero_slide(obj, expected_version=cms_version(obj), actor=cms_actor)
    return obj


def test_validation() -> None:
    hero = HomeSection.objects.create(kind="hero")
    with pytest.raises(ValidationError, match="Agrega una imagen"):
        HeroSlide(section=hero, alt_es="A", alt_en="A").full_clean()
    other = HomeSection.objects.create(kind="story")
    with pytest.raises(ValidationError, match="portada"):
        HeroSlide(section=other, image=upload((100, 100)), alt_es="A", alt_en="A").clean()
    with pytest.raises(ValidationError, match="alternativo"):
        HeroSlide(section=hero, image=upload((100, 100))).full_clean()
    with pytest.raises(ValidationError):
        slide(hero, image=ContentFile(b"bad", name="bad.png"))


def test_pipeline_and_clearing(cms_actor) -> None:
    hero = HomeSection.objects.create(kind="hero")
    obj = slide(hero, image=upload((1921, 900)))
    mobile = slide(hero, device="mobile", image=upload((1195, 1481)))
    assert (obj.width, obj.height) == (1921, 900)
    assert (mobile.width, mobile.height) == (1195, 1481)
    assert set(obj.renditions["webp"]) == {"960", "1600", "1921"}  # source width kept
    assert set(mobile.renditions["webp"]) == {"480", "960", "1195"}  # source width kept
    paths = file_paths(obj)
    services.save_hero_slide(obj, expected_version=cms_version(obj), actor=cms_actor)
    assert file_paths(obj) == paths
    obj.image = ""
    with pytest.raises(ValidationError, match="Agrega una imagen"):
        services.save_hero_slide(obj, expected_version=cms_version(obj), actor=cms_actor)
    capped = slide(hero, image=upload((3000, 1500)))
    assert (capped.width, capped.height) == (2400, 1200)
    assert set(capped.renditions["webp"]) == {"960", "1600", "2400"}


def test_snapshot_api_restore_and_schema(cms_actor, actor: User, client: Client) -> None:
    from drf_spectacular.generators import SchemaGenerator

    HomeSection.objects.all().delete()
    hero = HomeSection.objects.create(kind="hero", title_es="Portada")
    second = slide(hero, position=2, image=upload((1921, 900)))
    first = slide(hero, position=1, device="mobile", image=upload((750, 1000)))
    HeroSlide.objects.create(section=hero, image="unprocessed.png", alt_es="A", alt_en="A")
    # Unprocessed uploads are omitted from the public contract.
    publication = services.publish_home(actor, expected_version=cms_version())
    payload = client.get("/api/v1/cms/home").json()["sections"][0]
    assert payload["slides"][0]["mobile_image"] is None
    assert payload["slides"][1]["image"] is None
    assert payload["image"] == payload["slides"][0]["image"]
    assert len(payload["slides"]) == 2
    assert set(payload["slides"][0]) == {"image", "mobile_image"}
    assert set(payload["slides"][1]["mobile_image"]) == {"src", "srcset", "width", "height", "alt"}
    assert HeroSerializer(payload).data["slides"] == payload["slides"]
    assert publication.snapshot["en"][0]["slides"][1]["mobile_image"]["alt"] == "Stone"
    first.alt_es = "Borrador"
    services.save_hero_slide(first, expected_version=cms_version(first), actor=cms_actor)
    services.delete_hero_slide(second, expected_version=cms_version(second), actor=cms_actor)
    assert client.get("/api/v1/cms/home").json()["sections"][0] == payload
    assert selectors.home("es", preview=True)["sections"][0] != payload
    services.restore_home(publication, actor, expected_version=cms_version())
    assert list(
        HeroSlide.objects.filter(section_id=hero.pk).values_list("position", flat=True)
    ) == [0, 1, 2]
    assert selectors.home("es", preview=True)["sections"][0] == payload
    services.publish_home(actor, expected_version=cms_version())
    assert client.get("/api/v1/cms/home").json()["sections"][0] == payload
    schema = SchemaGenerator().get_schema(request=None, public=True)
    assert schema is not None
    components = schema["components"]["schemas"]
    assert components["Hero"]["properties"]["slides"]["items"]["$ref"].endswith("HeroSlide")
    assert set(components["HeroSlide"]["properties"]) == {"image", "mobile_image"}


def test_compatibility_image() -> None:
    hero = HomeSection.objects.create(kind="hero", image="legacy.webp")
    assert selectors.render_sections([hero], "es")[0]["image"]["src"].endswith("legacy.webp")
    first = slide(hero, image=upload((1921, 900)))
    assert selectors.render_sections([hero], "es")[0]["image"] == selectors.image_data(first, "es")


def test_cleanup_and_publication_protection(
    cms_actor, actor: User, django_capture_on_commit_callbacks: Any
) -> None:
    hero = HomeSection.objects.create(kind="hero")
    obj = slide(hero, image=upload((1000, 500)))
    paths = file_paths(obj)
    with django_capture_on_commit_callbacks(execute=True):
        services.delete_hero_slide(obj, expected_version=cms_version(obj), actor=cms_actor)
    assert all(not default_storage.exists(path) for path in paths)
    obj = slide(hero, image=upload((1000, 500)))
    paths = file_paths(obj)
    services.publish_home(actor, expected_version=cms_version())
    with django_capture_on_commit_callbacks(execute=True):
        obj.image = upload((1100, 550))
        services.save_hero_slide(obj, expected_version=cms_version(obj), actor=cms_actor)
    assert all(default_storage.exists(path) for path in paths)
    with django_capture_on_commit_callbacks(execute=True):
        services.delete_hero_slide(obj, expected_version=cms_version(obj), actor=cms_actor)
    assert all(default_storage.exists(path) for path in paths)


def test_inline_renders_and_parent_permissions(actor: User, client: Client) -> None:
    hero = HomeSection.objects.create(kind="hero")
    slide(hero, image=upload((1000, 500)))
    client.force_login(actor)
    device = TOTPDevice.objects.create(user=actor, confirmed=True)
    session = client.session
    session[DEVICE_ID_SESSION_KEY] = device.persistent_id
    session.save()
    response = client.get(reverse("admin:cms_homesection_change", args=[hero.pk]))
    assert response.status_code == 200
    assert "Fotos para computador (horizontales)" in response.content.decode()
    assert "1920 × 900 px" in response.content.decode()  # noqa: RUF001
    assert "field-image_alt" not in response.content.decode()
    assert "Fotos para celular (verticales)" in response.content.decode()
    assert "1080 × 1350 px" in response.content.decode()  # noqa: RUF001
    request = RequestFactory().get("/")
    editor = User.objects.create_user(username="slides-editor", is_staff=True)
    editor.user_permissions.add(Permission.objects.get(codename="change_homesection"))
    request.user = editor
    inline = HeroSlideInline(HomeSection, admin.site)
    assert inline.has_change_permission(request, hero)
    assert inline.has_add_permission(request, hero)
    assert inline.has_delete_permission(request, hero)
    parent = HomeSectionAdmin(HomeSection, admin.site)
    assert parent.get_inlines(request, hero) == (HeroSlideInline, MobileHeroSlideInline)
    assert parent.get_inlines(request, HomeSection(kind="story")) == ()


def test_restore_preserves_incomplete_hidden_drafts(actor: User) -> None:
    hidden = HomeSection.objects.create(kind="collection_rail", is_visible=False)
    publication = services.publish_home(actor, expected_version=cms_version())
    services.restore_home(publication, actor, expected_version=cms_version())
    assert not HomeSection.objects.get(pk=hidden.pk).is_visible


def test_admin_inline_upload_validation_save_and_delete(actor: User, client: Client) -> None:
    hero = HomeSection.objects.create(kind="hero")
    client.force_login(actor)
    device = TOTPDevice.objects.create(user=actor, confirmed=True)
    session = client.session
    session[DEVICE_ID_SESSION_KEY] = device.persistent_id
    session.save()
    url = reverse("admin:cms_homesection_change", args=[hero.pk])
    data: dict[str, Any] = {
        "kind": "hero",
        "position": 0,
        "is_visible": "on",
        "cta_kind": "none",
        "slides-2-TOTAL_FORMS": 1,
        "slides-2-INITIAL_FORMS": 0,
        "slides-2-MIN_NUM_FORMS": 0,
        "slides-2-MAX_NUM_FORMS": 1000,
        "slides-2-0-position": 0,
        "slides-2-0-alt_es": "Celular",
        "slides-2-0-alt_en": "Phone",
        "slides-TOTAL_FORMS": 1,
        "slides-INITIAL_FORMS": 0,
        "slides-MIN_NUM_FORMS": 0,
        "slides-MAX_NUM_FORMS": 1000,
        "slides-0-position": 0,
        "slides-0-alt_es": "Piedra",
        "slides-0-alt_en": "Stone",
    }
    response = client.post(
        url,
        cms_form_data(
            url,
            data
            | {
                "slides-0-image": ContentFile(b"bad", name="bad.png"),
                "slides-2-0-image": upload((750, 1000)),
            },
        ),
    )
    assert response.status_code == 200
    assert not hero.slides.exists()
    response = client.post(
        url,
        cms_form_data(
            url,
            data | {"slides-0-image": upload((1921, 900)), "slides-2-0-image": upload((750, 1000))},
        ),
    )
    assert response.status_code == 302
    obj = hero.slides.get(device="desktop")
    mobile = hero.slides.get(device="mobile")
    assert (obj.width, obj.height, mobile.width, mobile.height) == (1921, 900, 750, 1000)
    assert set(mobile.renditions["webp"]) == {"480", "750"}
    response = client.post(
        url,
        cms_form_data(
            url,
            data
            | {
                "slides-INITIAL_FORMS": 1,
                "slides-0-id": obj.pk,
                "slides-0-DELETE": "on",
                "slides-2-INITIAL_FORMS": 1,
                "slides-2-0-id": mobile.pk,
                "slides-2-0-DELETE": "on",
            },
        ),
    )
    assert response.status_code == 302
    assert not hero.slides.exists()


def test_admin_reorders_each_device_through_services(actor: User, client: Client) -> None:
    from unittest.mock import patch

    hero = HomeSection.objects.create(kind="hero")
    rows = {
        device: [slide(hero, device=device, position=i, image=upload((100, 100))) for i in range(2)]
        for device in ("desktop", "mobile")
    }
    client.force_login(actor)
    otp = TOTPDevice.objects.create(user=actor, confirmed=True)
    session = client.session
    session[DEVICE_ID_SESSION_KEY] = otp.persistent_id
    session.save()
    data: dict[str, Any] = {"position": 0, "is_visible": "on", "cta_kind": "none"}
    for device, prefix in (("desktop", "slides"), ("mobile", "slides-2")):
        data.update(
            {
                f"{prefix}-TOTAL_FORMS": 2,
                f"{prefix}-INITIAL_FORMS": 2,
                f"{prefix}-MIN_NUM_FORMS": 0,
                f"{prefix}-MAX_NUM_FORMS": 1000,
            }
        )
        for i, row in enumerate(rows[device]):
            data.update(
                {
                    f"{prefix}-{i}-id": row.pk,
                    f"{prefix}-{i}-position": 1 - i,
                    f"{prefix}-{i}-alt_es": "Foto",
                    f"{prefix}-{i}-alt_en": "Photo",
                }
            )
    with patch("apps.cms.admin.services.save_hero_slide", wraps=services.save_hero_slide) as save:
        response = client.post(
            reverse("admin:cms_homesection_change", args=[hero.pk]),
            cms_form_data(reverse("admin:cms_homesection_change", args=[hero.pk]), data),
        )
    assert response.status_code == 302
    assert save.call_count == 4
    for device in ("desktop", "mobile"):
        assert list(hero.slides.filter(device=device).values_list("pk", flat=True)) == [
            rows[device][1].pk,
            rows[device][0].pk,
        ]
