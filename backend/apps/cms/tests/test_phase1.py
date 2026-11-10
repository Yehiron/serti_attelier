from importlib import import_module

import pytest
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import Client, RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.roles import CONTENIDO, OPERACIONES, PROPIETARIO
from apps.audit.models import AuditLog
from apps.cms import editor_services, selectors, services
from apps.cms.admin import HomeSectionAdmin, PageAdmin
from apps.cms.api.serializers import CategoryGridSerializer, PageSerializer
from apps.cms.history import summary
from apps.cms.models import FaqItem, HomePublication, HomeSection, Page, PageRevision, ProcessStep
from apps.cms.tests.helpers import cms_form_data, cms_version

pytestmark = pytest.mark.django_db


@pytest.fixture
def actor():
    return User.objects.create_superuser(
        username="fase1", email="fase1@example.com", password="test"
    )


@pytest.fixture
def page():
    return Page.objects.get(kind="personalize")


@pytest.mark.parametrize(
    ("model", "field", "limit"),
    [
        (ProcessStep, "title", 60),
        (ProcessStep, "description", 240),
        (FaqItem, "question", 160),
        (FaqItem, "answer", 1500),
    ],
)
def test_limits(page, model, field, limit):
    values = (
        {"title_es": "Paso"}
        if model is ProcessStep
        else {"question_es": "Pregunta", "answer_es": "Respuesta"}
    )
    values[f"{field}_es"] = "a" * (limit + 1)
    with pytest.raises(ValidationError):
        model(page=page, **values).full_clean()
    values[f"{field}_es"] = "a" * limit
    model(page=page, **values).full_clean()


def test_step_only_personalize():
    with pytest.raises(ValidationError):
        ProcessStep(page=Page.objects.get(kind="contact"), title_es="Paso").full_clean()


def test_markdown_safety():
    rendered = services.render_markdown(
        "[Devoluciones](/es/legal/devoluciones) [malo](javascript:alert(1)) "
        "<script>alert(1)</script>"
    )
    assert 'href="/es/legal/devoluciones"' in rendered
    assert 'href="javascript:' not in rendered
    assert "<script>" not in rendered
    assert 'href="//' not in services.render_markdown("[malo](//evil.example)")


def test_publish_restore_and_old_snapshot(cms_actor, page, actor):
    faq = page.faq_items.first()
    faq.answer_es, faq.answer_en = "Respuesta nueva", "New answer"
    services.save_page_item(faq, actor=actor, expected_version=cms_version(faq))
    revision = services.publish_page(page, actor, expected_version=cms_version(page))
    assert revision.snapshot["en"]["faq"]["items"][0]["answer_html"] == "<p>New answer</p>"
    faq.answer_es = "Borrador posterior"
    services.save_page_item(faq, expected_version=cms_version(faq), actor=cms_actor)
    assert (
        selectors.page_payload(page, "es", revision)["faq"]["items"][0]["answer_html"]
        == "<p>Respuesta nueva</p>"
    )
    services.restore_page_revision(revision, actor, expected_version=cms_version(revision))
    assert page.faq_items.first().answer_es == "Respuesta nueva"
    assert page.faq_items.first().answer_en == "New answer"
    payload = selectors.page_payload(page, "es", revision)
    serialized = dict(PageSerializer(payload).data)
    assert serialized.keys() == payload.keys()
    assert serialized["process"] == payload["process"]
    assert serialized["faq"] == payload["faq"]
    snapshot = {
        lang: {
            key: value
            for key, value in revision.snapshot[lang].items()
            if key not in ("process", "faq", "process_title", "faq_title")
        }
        for lang in ("es", "en")
    }
    old = PageRevision.objects.create(page=page, version=revision.version + 1, snapshot=snapshot)
    assert "faq" not in selectors.page_payload(page, "es", old)
    services.restore_page_revision(old, actor, expected_version=cms_version(old))
    assert page.faq_items.count() == 4


def test_seed_idempotent_and_reverse(page):
    migration = import_module("apps.cms.migrations.0013_personalize_editorial_content")
    # Use historical models: immutable runtime managers intentionally prohibit deletion.
    from django.db.migrations.executor import MigrationExecutor

    historical = (
        MigrationExecutor(connection)
        .loader.project_state([("cms", "0013_personalize_editorial_content")])
        .apps
    )
    editor = connection.schema_editor()
    from apps.cms.models import ContentDocument

    ContentDocument.objects.update(page_revision=None)
    migration.unseed(historical, editor)
    from apps.cms.models import ContentDocument

    ContentDocument.objects.update(page_revision=None)
    migration.unseed(historical, editor)
    count = page.revisions.count()
    migration.seed(historical, editor)
    migration.seed(historical, editor)
    assert page.process_steps.count() == 4
    assert page.faq_items.count() == 4
    assert page.revisions.count() == count + 1
    assert "/es/legal/devoluciones" in page.faq_items.all()[2].answer_es
    from apps.cms.models import ContentDocument

    ContentDocument.objects.update(page_revision=None)
    migration.unseed(historical, editor)
    assert page.process_steps.count() == 0
    assert page.faq_items.count() == 0
    assert page.revisions.count() == count


@pytest.mark.parametrize(
    ("role", "status"), [(PROPIETARIO, 200), (CONTENIDO, 200), (OPERACIONES, 403)]
)
def test_history_roles(role, status):
    from apps.core.tests.test_dashboard_client import staff

    # staff() also verifies the TOTP session that Propietario requires.
    client, _user = staff(role)
    assert client.get(reverse("cms-history")).status_code == status


def test_history_confirmation_csrf_and_queries(page, actor):
    revision = services.publish_page(page, actor, expected_version=cms_version(page))
    from django_otp import DEVICE_ID_SESSION_KEY
    from django_otp.plugins.otp_totp.models import TOTPDevice

    client = Client(enforce_csrf_checks=True)
    client.force_login(actor)
    # Superusers must hold a verified second factor before reaching the dashboard.
    session = client.session
    session[DEVICE_ID_SESSION_KEY] = TOTPDevice.objects.create(
        user=actor, confirmed=True
    ).persistent_id
    session.save()
    url = reverse("cms-history") + f"?document={page.pk}&restore={revision.pk}"
    response = client.get(url)
    assert "La tienda no cambia hasta que publiques." in response.content.decode()
    assert client.post(url, cms_form_data(url, {"confirm": "yes"})).status_code == 403
    token = client.cookies["csrftoken"].value
    assert (
        client.post(
            url, cms_form_data(url, {"confirm": "yes", "csrfmiddlewaretoken": token})
        ).status_code
        == 302
    )
    for index in range(22):
        page.title_es = f"Publicación {index}"
        services.save_page(page, actor=actor, expected_version=cms_version(page))
        services.publish_page(page, actor, expected_version=cms_version(page))
    with CaptureQueriesContext(connection) as queries:
        response = client.get(reverse("cms-history") + f"?document={page.pk}")
    assert response.status_code == 200
    assert len(response.context_data["rows"]) == 20
    assert len(queries) < 25
    assert "snapshot" not in response.content.decode()
    with CaptureQueriesContext(connection) as queries:
        selectors.page_payload(Page.objects.get(pk=page.pk), "es")
    assert len(queries) <= 5


def test_human_summary():
    before = {"es": [{"id": 1, "title": "Antes", "image": None}, {"id": 2, "title": "Historia"}]}
    after = {"es": [{"id": 1, "title": "Después", "image": {"src": "photo"}}]}
    changes = " ".join(summary(after, before, home=True))
    assert "Antes → Después" in changes
    assert "Fotos cambiadas" in changes
    assert "oculta" in changes
    assert '"id"' not in changes


def test_audit_save_and_visibility_reorder(page, actor):
    request = RequestFactory().post("/", HTTP_USER_AGENT="CMS prueba")
    faq = page.faq_items.first()
    faq.question_es = "¿Qué cambió?"
    services.save_page_item(faq, actor=actor, request=request, expected_version=cms_version(faq))
    event = AuditLog.objects.latest("pk")
    assert event.actor == actor and event.user_agent == "CMS prueba"
    assert any("¿Qué cambió?" in values for values in event.diff.values())
    page.title_es = "Personaliza conmigo"
    services.save_page(page, actor=actor, request=request, expected_version=cms_version(page))
    section = HomeSection.objects.create(kind="statement", title_es="Antes")
    section.title_es = "Después"
    services.save_section(
        section, actor=actor, request=request, expected_version=cms_version(section)
    )
    event = AuditLog.objects.latest("pk")
    assert any(values == ["Antes", "Después"] for values in event.diff.values())
    start = AuditLog.objects.count()
    editor_services.set_section_visibility(
        section, False, actor=actor, request=request, expected_version=cms_version()
    )
    assert AuditLog.objects.count() == start + 1
    rows = list(HomeSection.objects.values_list("pk", flat=True))
    start = AuditLog.objects.count()
    editor_services.reorder_sections(
        list(reversed(rows)), actor=actor, request=request, expected_version=cms_version()
    )
    assert AuditLog.objects.count() == start + 1
    assert AuditLog.objects.latest("pk").actor == actor


def test_category_schema_and_subtitle(actor):
    section = HomeSection.objects.create(
        kind="category_grid", title_es="Categorías", subtitle_es="Escoge tu joya"
    )
    request = RequestFactory().get("/")
    request.user = actor
    fields = str(HomeSectionAdmin(HomeSection, admin.site).get_fieldsets(request, section))
    assert "subtitle_es" in fields
    data = selectors.resolve_live(selectors.render_sections([section], "es"), "es")[0]
    assert dict(CategoryGridSerializer(data).data) == data


def test_home_hidden_vs_unpublished(actor):
    # Historical manager is not needed: use a savepoint-safe raw queryset for immutable setup.
    from django.db.models import QuerySet

    QuerySet(model=HomePublication).delete()
    assert selectors.home("es")["published_at"] is None
    HomeSection.objects.all().update(is_visible=False)
    services.publish_home(actor, expected_version=cms_version())
    data = selectors.home("es")
    assert data["sections"] == [] and data["published_at"] is not None


def test_personalize_form_note_and_hidden_body(page, actor):
    request = RequestFactory().get("/")
    request.user = actor
    fields = str(PageAdmin(Page, admin.site).get_fieldsets(request, page))
    assert "body_es" not in fields
    assert "Esta página muestra los pasos" in fields


def test_home_api_matches_category_schema(actor):
    from drf_spectacular.generators import SchemaGenerator

    from apps.catalog.models import Category

    HomeSection.objects.all().update(is_visible=False)
    HomeSection.objects.create(kind="category_grid", is_visible=True, title_es="Categorías")
    Category.objects.get_or_create(slug_es="fase1", defaults={"name_es": "Categoría de prueba"})
    services.publish_home(actor, expected_version=cms_version())
    response = Client().get(reverse("cms-home"), {"locale": "es"})
    assert response.status_code == 200
    data = response.json()
    schema = SchemaGenerator().get_schema(request=None, public=True)
    properties = schema["components"]["schemas"]["HomeCategory"]["properties"]
    for category in data["sections"][0]["categories"]:
        assert set(category) == set(properties)
    assert set(data) == {"sections", "published_at", "preview", "seo"}


@pytest.mark.parametrize("kind", ["story", "personalize", "banner"])
def test_photo_and_slide_audits(actor, settings, tmp_path, kind):
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    from apps.cms.models import HeroSlide

    settings.MEDIA_ROOT = tmp_path

    def photo():
        buffer = BytesIO()
        Image.new("RGB", (100, 100), "white").save(buffer, format="PNG")
        return SimpleUploadedFile("photo.png", buffer.getvalue(), content_type="image/png")

    request = RequestFactory().post("/", HTTP_USER_AGENT="Fotos CMS")
    section = HomeSection.objects.create(kind=kind, title_es="Historia")
    for _ in range(2):
        before = AuditLog.objects.count()
        editor_services.replace_section_image(
            section, photo(), actor=actor, request=request, expected_version=cms_version()
        )
        assert AuditLog.objects.count() == before + 1
        assert AuditLog.objects.latest("pk").actor == actor
    event = AuditLog.objects.latest("pk")
    assert event.diff["Foto"] == ["Foto anterior", "Foto reemplazada"]
    hero = HomeSection.objects.create(kind="hero", title_es="Portada")
    before = AuditLog.objects.count()
    editor_services.upload_hero_photos(
        hero,
        "desktop",
        [photo(), photo()],
        actor=actor,
        request=request,
        expected_version=cms_version(),
    )
    assert AuditLog.objects.count() == before + 1
    slides = list(hero.slides.all())
    before = AuditLog.objects.count()
    editor_services.reorder_hero_slides(
        hero,
        "desktop",
        [s.pk for s in reversed(slides)],
        actor=actor,
        request=request,
        expected_version=cms_version(),
    )
    assert AuditLog.objects.count() == before + 1
    slide = HeroSlide.objects.get(pk=slides[0].pk)
    slide.alt_es = "Foto nueva"
    before = AuditLog.objects.count()
    services.save_hero_slide(
        slide, actor=actor, request=request, expected_version=cms_version(slide)
    )
    assert AuditLog.objects.count() == before + 1
    before = AuditLog.objects.count()
    services.delete_hero_slide(
        slide, actor=actor, request=request, expected_version=cms_version(slide)
    )
    assert AuditLog.objects.count() == before + 1


def test_admin_saves_pass_actor_request(page, actor):
    from unittest.mock import patch

    request = RequestFactory().post("/")
    request.user = actor
    with patch("apps.cms.services.save_page") as save:
        PageAdmin(Page, admin.site).save_model(request, page, None, True)
    save.assert_called_once_with(page, actor=actor, request=request)
    section = HomeSection.objects.first()
    with patch("apps.cms.services.save_section") as save:
        HomeSectionAdmin(HomeSection, admin.site).save_model(request, section, None, True)
    save.assert_called_once_with(section, actor=actor, request=request)


def test_seed_preserves_unrelated_draft_and_reverse_keeps_edited_rows(page, actor):
    from django.db.migrations.executor import MigrationExecutor

    migration = import_module("apps.cms.migrations.0013_personalize_editorial_content")
    historical = (
        MigrationExecutor(connection)
        .loader.project_state([("cms", "0013_personalize_editorial_content")])
        .apps
    )
    editor = connection.schema_editor()
    from apps.cms.models import ContentDocument

    ContentDocument.objects.update(page_revision=None)
    migration.unseed(historical, editor)
    page.refresh_from_db()
    published = services.publish_page(page, actor, expected_version=cms_version(page))
    page.title_es = "Título que todavía no quiero publicar"
    services.save_page(page, actor=actor, expected_version=cms_version(page))
    migration.seed(historical, editor)
    page.refresh_from_db()
    assert page.title_es == "Título que todavía no quiero publicar"
    assert page.revisions.first().snapshot["es"]["title"] == published.snapshot["es"]["title"]
    faq = page.faq_items.first()
    faq.answer_es = "Respuesta editada después de migrar"
    services.save_page_item(faq, actor=actor, expected_version=cms_version(faq))
    from apps.cms.models import ContentDocument

    ContentDocument.objects.update(page_revision=None)
    migration.unseed(historical, editor)
    assert FaqItem.objects.filter(pk=faq.pk, answer_es=faq.answer_es).exists()
    assert page.faq_items.count() == 1


def test_delete_faq_and_step_audits(page, actor):
    request = RequestFactory().post("/")
    for row in [page.faq_items.first(), page.process_steps.first()]:
        count = AuditLog.objects.count()
        services.delete_page_item(
            row, actor=actor, request=request, expected_version=cms_version(row)
        )
        assert AuditLog.objects.count() == count + 1
        event = AuditLog.objects.latest("pk")
        assert event.actor == actor
        assert event.diff["Contenido"][1] == "Eliminado del borrador"
