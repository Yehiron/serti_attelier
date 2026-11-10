"""Three panel editor integration: deliberately uses the configured PostgreSQL DB."""

import json
from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from apps.accounts.roles import CONTENIDO, OPERACIONES, PROPIETARIO
from apps.audit.models import AuditLog
from apps.cms import services
from apps.cms.documents import get_document
from apps.cms.models import DraftRevision, FaqItem, HomeSection, Page, ProcessStep
from apps.core.tests.test_dashboard_client import staff


@pytest.fixture
def owner(db):
    return staff(PROPIETARIO)


def send(browser, action, key="home", version=None, **data):
    if version is None:
        version = get_document(key).draft_version
    return browser.post(
        reverse("cms-editor-document") + "?document=" + key,
        json.dumps({"action": action, "expected_version": version, **data}),
        content_type="application/json",
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role,allowed", [(PROPIETARIO, True), (CONTENIDO, True), (OPERACIONES, False)]
)
def test_roles(role, allowed):
    browser, _ = staff(role)
    url = reverse("cms-editor-document")
    assert browser.get(url).status_code == (200 if allowed else 403)
    response = send(
        browser, "create", kind="statement", values={"title": {"es": "Hola", "en": "Hello"}}
    )
    assert response.status_code == (200 if allowed else 403)
    editor = browser.get(reverse("visual-editor"))
    assert editor.status_code == (200 if allowed else 403)
    if allowed:
        assert (b'id="cms-review"' in editor.content) == (role == PROPIETARIO)


@pytest.mark.django_db
def test_anonymous_and_csrf(owner):
    browser, _user = owner
    assert Client().get(reverse("cms-editor-document")).status_code == 403
    strict = Client(enforce_csrf_checks=True)
    strict.cookies = browser.cookies
    assert (
        strict.post(
            reverse("cms-editor-document"), "{}", content_type="application/json"
        ).status_code
        == 403
    )
    editor = strict.get(reverse("visual-editor"))
    token = strict.cookies["csrftoken"].value
    assert editor.status_code == 200
    assert editor.headers["X-Frame-Options"] == "DENY"
    assert (
        strict.post(
            reverse("cms-editor-document"),
            json.dumps(
                {
                    "action": "create",
                    "kind": "statement",
                    "values": {},
                    "expected_version": get_document("home").draft_version,
                }
            ),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        ).status_code
        == 200
    )


@pytest.mark.django_db
def test_conflicts_validation_and_structural_audit(owner):
    browser, _ = owner
    response = send(
        browser, "create", kind="statement", values={"title": {"es": "Inicial", "en": "Initial"}}
    )
    assert response.status_code == 200
    data = response.json()
    pk = data["selected"]
    version = data["version"]
    assert (
        send(browser, "update", id=pk, values={"title": {"es": "x" * 301, "en": ""}}).status_code
        == 400
    )
    assert get_document("home").draft_version == version
    assert send(browser, "update", id=pk, version=version - 1, values={}).status_code == 409
    assert send(browser, "create", kind="unknown", values={}).status_code == 400
    assert send(browser, "visibility", id=pk, visible=False).status_code == 200
    copy = send(browser, "duplicate", id=pk).json()["selected"]
    ids = [
        str(i) for i in HomeSection.objects.order_by("position", "pk").values_list("pk", flat=True)
    ]
    assert send(browser, "reorder", ids=list(reversed(ids))).status_code == 200
    assert send(browser, "delete", id=copy).status_code == 200
    assert get_document("home").draft_version == version + 4
    for action in ("cms.section_duplicated", "cms.section_deleted", "cms.sections_reordered"):
        assert AuditLog.objects.filter(action=action).exists()
    assert send(browser, "update", id=pk, values={"title": {"es": "x" * 301, "en": ""}}).json()[
        "fields"
    ]["title.es"]


@pytest.mark.django_db
def test_bindings_and_document_composition(owner):
    browser, _ = owner
    page = Page.objects.get_or_create(
        kind="personalize", defaults={"title_es": "Personaliza", "slug_es": "personaliza"}
    )[0]
    count = HomeSection.objects.count()
    payload = {
        "title": {"es": "Pasos", "en": "Steps"},
        "steps": [
            {"title": {"es": "Conversamos", "en": "Talk"}, "description": {"es": "", "en": ""}},
            {"title": {"es": "Creamos", "en": "Create"}, "description": {"es": "", "en": ""}},
        ],
    }
    response = send(browser, "update", key="page:personalize", id="process", values=payload)
    assert response.status_code == 200
    assert ProcessStep.objects.filter(page=page).count() == 2
    assert HomeSection.objects.count() == count
    assert not FaqItem.objects.filter(page=page, question_es="Conversamos").exists()
    assert (
        send(browser, "create", key="page:personalize", kind="image_text", values={}).status_code
        == 400
    )
    assert (
        send(browser, "visibility", key="page:personalize", id="process", visible=False).status_code
        == 400
    )
    assert get_document("page:personalize").draft_version == response.json()["version"]


@pytest.mark.django_db
def test_discard_is_versioned_restore_and_content_cannot_discard(owner):
    browser, actor = owner
    section = HomeSection.objects.create(kind="statement", title_es="Publicado")
    services.publish_home(actor, expected_version=get_document("home").draft_version)
    send(browser, "update", id=str(section.pk), values={"title": {"es": "Borrador", "en": "Draft"}})
    old = get_document("home").draft_version
    assert send(browser, "discard", version=old - 1).status_code == 409
    assert send(browser, "discard", version=old).status_code == 200
    assert HomeSection.objects.get(pk=section.pk).title_es == "Publicado"
    assert DraftRevision.objects.filter(document__key="home", draft_version=old + 1).exists()
    content, _ = staff(CONTENIDO)
    assert send(content, "discard").status_code == 403


def test_default_framing_and_caddy_scope():
    assert settings.X_FRAME_OPTIONS == "DENY"
    repo = Path(__file__).resolve().parents[4]
    for name in ("Caddyfile", "Caddyfile.dev"):
        source = (repo / "infra" / name).read_text()
        assert "path /es /en /es/* /en/*" in source
        assert "-X-Frame-Options" in source
        assert "frame-ancestors 'self'" in source
        assert "frame-ancestors 'none'" in source


@pytest.mark.django_db
def test_missing_version_and_draft_cookie_do_not_bypass_security(owner):
    browser, _actor = owner
    browser.cookies["__prerender_bypass"] = "untrusted-cookie"
    response = browser.get(reverse("cms-editor-document"))
    assert response.headers["X-Frame-Options"] == "DENY"
    version = get_document("home").draft_version
    response = browser.post(
        reverse("cms-editor-document"),
        json.dumps({"action": "create", "kind": "statement", "values": {}}),
        content_type="application/json",
    )
    assert response.status_code == 409
    assert get_document("home").draft_version == version


def test_readable_page_comparison_contains_fields_and_both_languages():
    from apps.cms.history import summary

    before = {
        lang: {
            "faq": {
                "title": "FAQ",
                "items": [{"source": {"question": "Antes", "answer": "Respuesta anterior"}}],
            }
        }
        for lang in ("es", "en")
    }
    after = {
        lang: {
            "faq": {
                "title": "FAQ",
                "items": [{"source": {"question": "Después", "answer": "Respuesta nueva"}}],
            }
        }
        for lang in ("es", "en")
    }
    changes = summary(after, before)
    for language in ("español", "inglés"):
        assert any(f"Pregunta ({language}): Antes → Después" in line for line in changes)
        assert any("Respuesta anterior → Respuesta nueva" in line for line in changes)


@pytest.mark.django_db
def test_photo_slot_requires_bilingual_alt_and_a_version(owner, settings, tmp_path):
    from apps.cms.tests.test_hero_slides import upload

    settings.MEDIA_ROOT = tmp_path
    browser, _actor = owner
    url = reverse("cms-editor-photo")
    version = get_document("home").draft_version
    payload = {
        "section": "new",
        "kind": "image_text",
        "slot": "image",
        "expected_version": version,
        "alt_es": "Foto",
        "alt_en": "",
    }
    assert browser.post(url, {**payload, "file": upload((100, 120))}).status_code == 400
    assert get_document("home").draft_version == version
    result = browser.post(url, {**payload, "alt_en": "Photo", "file": upload((100, 120))})
    assert result.status_code == 200
    assert result.json()["version"] == version + 1
    assert result.json()["image"]["alt"] == {"es": "Foto", "en": "Photo"}
    assert AuditLog.objects.filter(action="cms.editor_photo_uploaded").exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role,allowed", [(PROPIETARIO, True), (CONTENIDO, True), (OPERACIONES, False)]
)
def test_carousel_version_permissions_and_audit(role, allowed, settings, tmp_path):
    from apps.cms.tests.test_hero_slides import upload

    settings.MEDIA_ROOT = tmp_path
    browser, actor = staff(role)
    hero = HomeSection.objects.create(kind="hero", title_es="Portada")
    version = get_document("home").draft_version
    url = reverse("cms-editor-photo")

    def photo(version):
        return browser.post(
            url,
            {
                "section": hero.pk,
                "device": "mobile",
                "expected_version": version,
                "file": [upload((80, 100)), upload((100, 120))],
            },
        )

    response = photo(version)
    assert response.status_code == (200 if allowed else 403)
    if not allowed:
        assert not hero.slides.exists()
        for action, extra in (
            ("hero-alt", {"slide": "1", "alt": {"es": "Foto", "en": "Photo"}}),
            ("hero-delete", {"slide": "1"}),
            ("hero-reorder", {"ids": []}),
        ):
            assert (
                send(browser, action, id=str(hero.pk), device="mobile", **extra).status_code == 403
            )
        return
    assert response.json()["version"] == version + 1
    slides = next(s for s in response.json()["sections"] if s["id"] == str(hero.pk))["values"][
        "slides"
    ]
    assert len(slides) == 2
    for item in slides:
        assert item["device"] == "mobile"
        assert item["thumbnail"] and item["thumbnail"] != hero.slides.get(pk=item["id"]).image.url
    assert AuditLog.objects.filter(action="cms.slides_uploaded", actor=actor).exists()
    assert (
        browser.post(
            url, {"section": hero.pk, "device": "mobile", "file": upload((80, 100))}
        ).status_code
        == 409
    )
    assert photo(version).status_code == 409
    assert hero.slides.count() == 2
    ids = [s["id"] for s in slides]
    assert (
        send(browser, "hero-reorder", id=str(hero.pk), device="mobile", ids=ids[::-1]).status_code
        == 200
    )
    assert list(hero.slides.values_list("pk", flat=True)) == [int(pk) for pk in ids[::-1]]
    assert AuditLog.objects.filter(action="cms.slides_reordered", actor=actor).exists()
    current = get_document("home").draft_version
    assert (
        send(
            browser,
            "hero-alt",
            id=str(hero.pk),
            device="mobile",
            slide=ids[0],
            alt={"es": "Nueva foto", "en": "New photo"},
            version=current - 1,
        ).status_code
        == 409
    )
    assert (
        send(
            browser,
            "hero-alt",
            id=str(hero.pk),
            device="mobile",
            slide=ids[0],
            alt={"es": "Nueva foto", "en": "New photo"},
        ).status_code
        == 200
    )
    assert hero.slides.get(pk=ids[0]).alt_en == "New photo"
    latest = get_document("home").draft_version
    assert (
        send(
            browser,
            "hero-alt",
            id=str(hero.pk),
            device="mobile",
            slide=ids[0],
            alt={"es": "Foto", "en": ""},
        ).status_code
        == 400
    )
    assert (
        send(
            browser, "hero-reorder", id=str(hero.pk), device="mobile", ids=[ids[0], ids[0]]
        ).status_code
        == 400
    )
    assert get_document("home").draft_version == latest
    audit = AuditLog.objects.get(
        action="cms.draft_saved",
        object_id=str(ids[0]),
        content_type__model="heroslide",
        actor=actor,
    )
    assert any(values[1] == "New photo" for values in audit.diff.values())
    assert (
        send(browser, "hero-delete", id=str(hero.pk), device="desktop", slide=ids[0]).status_code
        == 404
    )
    assert (
        send(
            browser, "hero-delete", id=str(hero.pk), device="mobile", slide=ids[0], version=current
        ).status_code
        == 409
    )
    assert (
        send(browser, "hero-delete", id=str(hero.pk), device="mobile", slide=ids[0]).status_code
        == 200
    )
    assert not hero.slides.filter(pk=ids[0]).exists()
    assert AuditLog.objects.filter(action="cms.slide_deleted", actor=actor).exists()
    assert get_document("home").draft_version == version + 4


@pytest.mark.django_db
@pytest.mark.parametrize("kind,field", [("statement", "body"), ("stone_panels", "subtitle")])
def test_title_only_preserves_empty_source_and_public_payload(owner, kind, field):
    from apps.cms.publishing import pending_changes

    browser, actor = owner
    section = HomeSection.objects.create(kind=kind, title_es="Antes", title_en="Before")
    # Historical rows may contain either null or empty translations.
    HomeSection.objects.filter(pk=section.pk).update(**{f"{field}_es": None, f"{field}_en": ""})
    published = services.publish_home(actor, expected_version=get_document("home").draft_version)
    before = published.snapshot
    assert (
        send(
            browser,
            "update",
            id=str(section.pk),
            values={"title": {"es": "Después", "en": "Before"}},
        ).status_code
        == 200
    )
    section.refresh_from_db()
    assert getattr(section, f"{field}_es") is None
    assert getattr(section, f"{field}_en") == ""
    pending = pending_changes("home")
    assert pending["count"] == 1
    assert "Título · español" in pending["changes"][0]
    review = browser.get(reverse("cms-review-publish", args=["home"]))
    assert review.status_code == 200
    assert review.content.decode().count('class="cms-change-row"') == 1
    assert review.context["pending_count"] == 1
    assert review.context["change_groups"] == pending["groups"]
    for lang in ("es", "en"):
        left = next(row for row in before[lang] if str(row["id"]) == str(section.pk))
        right = next(row for row in pending["snapshot"][lang] if str(row["id"]) == str(section.pk))
        assert {k: v for k, v in left.items() if k != "title"} == {
            k: v for k, v in right.items() if k != "title"
        }


def test_semantic_comparison_ignores_empty_and_missing_values():
    from apps.cms.review_changes import home_groups, page_groups

    before = [{"id": 1, "kind": "statement", "title_es": "Antes", "body_es": None}]
    after = [{"id": 1, "kind": "statement", "title_es": "Después", "body_es": "", "body_en": ""}]
    groups = home_groups(after, before)
    assert len(groups) == 1
    assert groups[0]["rows"] == [
        {"label": "Título · español", "before": "Antes", "after": "Después"}
    ]
    assert page_groups({"es": {"body": ""}}, {"es": {"body": None}}) == []
    assert page_groups({"es": {"body": "Uno\r\n\r\nDos"}}, {"es": {"body": "Uno\n\nDos"}}) == []


def test_page_comparison_does_not_duplicate_fallbacks_or_rendered_html():
    from copy import deepcopy

    from apps.cms.review_changes import page_groups

    before = {
        lang: {
            "title": "Antes",
            "body": "",
            "body_html": "",
            "source": {"title": "Antes", "body": None},
        }
        for lang in ("es", "en")
    }
    after = deepcopy(before)
    after["es"]["title"] = after["es"]["source"]["title"] = "Después"
    after["en"]["body"] = ""
    assert page_groups(after, before)[0]["rows"] == [
        {"label": "Título · español", "before": "Antes", "after": "Después"}
    ]


def test_legacy_summaries_ignore_empty_text_changes():
    from apps.cms.history import home_source_summary, summary

    assert (
        home_source_summary(
            [{"id": 1, "title_es": "Título", "body_es": "", "body_en": None}],
            [{"id": 1, "title_es": "Título", "body_es": None}],
        )
        == []
    )
    assert summary({"es": {"body": ""}}, {"es": {"body": None}}) == [
        "Sin cambios visibles en la tienda."
    ]
