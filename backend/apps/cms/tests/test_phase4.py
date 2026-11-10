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
