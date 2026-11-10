"""Editorial invariants. Integration and thread tests require real PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from threading import Barrier
from unittest.mock import patch

import pytest
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import RequestFactory
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.roles import CONTENIDO, OPERACIONES, PROPIETARIO
from apps.accounts.services import sync_roles
from apps.cms import selectors, services
from apps.cms.documents import ContentConflict, document_key, get_document
from apps.cms.history import summary
from apps.cms.models import ContentDocument, DraftRevision, HomePublication, HomeSection, Page
from apps.cms.preview import PreviewInvalid, make_token, verify_token
from apps.cms.publishing import pending_changes
from apps.core.dashboard import NAVIGATION
from apps.core.tests.test_dashboard_client import staff

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return staff(PROPIETARIO)


def version(key="home"):
    return get_document(key).draft_version


def publish(actor, page=None, **kwargs):
    key = document_key(page)
    kwargs.setdefault("expected_version", version(key))
    return (
        services.publish_page(page, actor, **kwargs)
        if page
        else services.publish_home(actor, **kwargs)
    )


def section_data(section, expected, title="Texto propio conservado"):
    return {
        "position": section.position,
        "is_visible": "on",
        "title_es": title,
        "title_en": "English",
        "body_es": "Texto",
        "body_en": "Text",
        "expected_version": expected,
        "_continue": "1",
    }


def test_admin_conflict_keeps_typed_values_and_one_increment(owner):
    browser, _user = owner
    section = HomeSection.objects.create(kind="statement", title_es="Inicial")
    url = reverse("admin:cms_homesection_change", args=[section.pk])
    expected = browser.get(url).context["adminform"].form["expected_version"].value()
    assert browser.post(url, section_data(section, expected, "Primer guardado")).status_code == 302
    assert version() == int(expected) + 1
    response = browser.post(url, section_data(section, expected))
    assert response.status_code == 200
    assert "Otra persona guardó cambios" in response.content.decode()
    assert "Ver versión actual" in response.content.decode()
    assert response.context["adminform"].form["title_es"].value() == "Texto propio conservado"
    section.refresh_from_db()
    assert section.title_es == "Primer guardado"
    assert version() == int(expected) + 1


def test_ajax_conflict(owner):
    browser, user = owner
    section = HomeSection.objects.create(kind="statement")
    expected = version()
    url = reverse("visual-editor-action", args=["section-visibility"])
    data = {"section": section.pk, "visible": "false", "expected_version": expected}
    assert browser.post(url, data).status_code == 200
    response = browser.post(url, data | {"visible": "true"})
    assert response.status_code == 409
    assert response.json()["conflict"] is True
    assert user.username in response.json()["error"]
    assert browser.post(url, {"section": section.pk, "visible": "true"}).status_code == 409
    section.refresh_from_db()
    assert not section.is_visible


def test_service_requires_actor_and_version(owner):
    _, user = owner
    row = HomeSection(kind="statement")
    with pytest.raises(PermissionDenied):
        services.save_section(row, expected_version=version())
    with pytest.raises(ContentConflict):
        services.save_section(row, actor=user)


@pytest.mark.parametrize("home", [True, False])
def test_exact_publish_double_click_and_pending_selector(owner, home):
    browser, user = owner
    page = None if home else Page.objects.get(kind="personalize")
    if home:
        HomeSection.objects.all().delete()
        row = HomeSection.objects.create(kind="statement", title_es="Antes")
    else:
        row = page
    first = publish(user, page)
    key = document_key(page)
    reviewed = version(key)
    row.title_es = "Cambio revisable"
    (services.save_section if home else services.save_page)(
        row, actor=user, expected_version=reviewed
    )
    pending = pending_changes(key)
    assert pending["count"] > 0
    assert any("Título" in item for item in pending["changes"])
    with pytest.raises(ContentConflict, match="El borrador cambió"):
        publish(user, page, expected_version=reviewed)
    expected = version(key)
    second = publish(user, page, expected_version=expected)
    assert second.pk != first.pk
    assert publish(user, page, expected_version=expected).pk == second.pk
    assert pending_changes(key)["count"] == 0
    response = browser.get(reverse("cms-review-publish", args=[key]))
    assert "No hay cambios pendientes" in response.content.decode()
    assert b"disabled" in response.content


@pytest.mark.parametrize("home", [True, False])
def test_snapshot_failure_rolls_back(owner, home):
    _, user = owner
    page = None if home else Page.objects.get(kind="personalize")
    if home:
        HomeSection.objects.all().delete()
        row = HomeSection.objects.create(kind="statement", title_es="Publicado")
    else:
        row = page
    first = publish(user, page)
    key = document_key(page)
    row.title_es = "Borrador siguiente"
    (services.save_section if home else services.save_page)(
        row, actor=user, expected_version=version(key)
    )
    model = HomePublication if home else type(first)
    with (
        patch.object(model.objects, "create", side_effect=RuntimeError("snapshot fallido")),
        pytest.raises(RuntimeError),
    ):
        publish(user, page)
    assert (HomePublication.objects.first() if home else page.revisions.first()).pk == first.pk
    document = get_document(key)
    assert (document.home_publication_id if home else document.page_revision_id) == first.pk
    assert pending_changes(key)["count"] > 0


@pytest.mark.parametrize("home", [True, False])
def test_restore_records_new_draft_without_publishing(owner, home):
    browser, user = owner
    page = None if home else Page.objects.get(kind="personalize")
    first = publish(user, page)
    key = document_key(page)
    expected = version(key)
    restore = services.restore_home if home else services.restore_page_revision
    count = (HomePublication.objects if home else page.revisions).count()
    restore(first, user, expected_version=expected)
    assert version(key) == expected + 1
    revision = DraftRevision.objects.get(document__key=key, draft_version=expected + 1)
    assert revision.kind == "restore" and revision.restored_from == first
    assert revision.published_by == user
    assert (HomePublication.objects if home else page.revisions).count() == count
    assert get_document(key).published_version == expected
    response = browser.get(reverse("cms-history"), {"document": "home" if home else page.pk})
    assert "Restaurado desde la publicación del" in response.content.decode()
    with pytest.raises(ContentConflict):
        restore(first, user, expected_version=expected)


@pytest.mark.parametrize(
    "role,edit,can_publish",
    [(PROPIETARIO, True, True), (CONTENIDO, True, False), (OPERACIONES, False, False)],
)
def test_role_services_http_and_menu(role, edit, can_publish):
    browser, user = staff(role)
    page = Page.objects.get(kind="personalize")
    key = document_key(page)
    section = HomeSection.objects.create(kind="statement")
    endpoints = [
        reverse("visual-editor"),
        reverse("admin:cms_page_change", args=[page.pk]),
        reverse("cms-history"),
    ]
    for url in endpoints:
        assert browser.get(url).status_code == (200 if edit else 403)
    assert browser.get(reverse("admin:cms-page-preview", args=[page.pk])).status_code == (
        302 if edit else 403
    )
    review = reverse("cms-review-publish", args=[key])
    assert browser.get(review).status_code == (200 if can_publish else 403)
    assert browser.post(review, {"expected_version": version(key)}).status_code == (
        302 if can_publish else 403
    )
    if edit:
        services.save_section(section, actor=user, expected_version=version())
        assert verify_token(make_token(user)).pk == user.pk
    else:
        with pytest.raises(PermissionDenied):
            services.save_section(section, actor=user, expected_version=version())
        with pytest.raises(PreviewInvalid):
            make_token(user)
    if not can_publish:
        with pytest.raises(PermissionDenied):
            publish(user, page)
        revision = page.revisions.first()
        with pytest.raises(PermissionDenied):
            services.restore_page_revision(revision, user, expected_version=version(key))
        assert (
            browser.get(
                reverse("cms-history"), {"document": page.pk, "restore": revision.pk}
            ).status_code
            == 403
        )
    if role == CONTENIDO:
        html = browser.get(reverse("visual-editor")).content.decode()
        assert "la Propietaria puede publicarlos" in html
        assert "Revisar y publicar" not in html
        assert "Publicar ahora" not in html
    if role == OPERACIONES:
        request = RequestFactory().get("/")
        request.user = user
        group = next(group for group in NAVIGATION if str(group.get("title")) == "Página web")
        assert all(not item["permission"](request) for item in group["items"])
        assert "Página web" not in browser.get(reverse("admin:index")).content.decode()


def test_preview_revocation_and_role_sync():
    _, user = staff(CONTENIDO)
    group = Group.objects.get(name=CONTENIDO)
    group.permissions.add(
        Permission.objects.get(content_type__app_label="cms", codename="publish_content")
    )
    sync_roles()
    user = User.objects.get(pk=user.pk)
    assert not user.has_perm("cms.publish_content")
    token = make_token(user)
    group.permissions.remove(
        Permission.objects.get(content_type__app_label="cms", codename="preview_content")
    )
    with pytest.raises(PreviewInvalid):
        verify_token(token)
    sync_roles()
    user = User.objects.get(pk=user.pk)
    token = make_token(user)
    user.is_active = False
    user.save()
    with pytest.raises(PreviewInvalid):
        verify_token(token)


def test_anonymous_services_and_http(client):
    row = HomeSection(kind="statement")
    with pytest.raises(PermissionDenied):
        services.save_section(row, actor=AnonymousUser(), expected_version=version())
    with pytest.raises(PermissionDenied):
        publish(AnonymousUser())
    for url in [
        reverse("visual-editor"),
        reverse("cms-history"),
        reverse("cms-review-publish", args=["home"]),
    ]:
        assert client.get(url).status_code == 302


def test_bilingual_summary_sections_photos_and_children():
    before = {
        lang: [
            {"id": 1, "title": "A", "image": "old", "body": "Antes"},
            {"id": 2, "title": "B"},
            {"id": 3, "title": "C"},
        ]
        for lang in ("es", "en")
    }
    after = {
        lang: [
            {"id": 3, "title": "Nuevo", "image": "new", "body": "Después"},
            {"id": 1, "title": "A"},
            {"id": 4, "title": "D"},
        ]
        for lang in ("es", "en")
    }
    changes = summary(after, before, home=True)
    for term in ["añadida", "oculta", "reordenadas", "Título", "Fotos", "Textos", "inglés"]:
        assert any(term in item for item in changes)
    changes = summary(
        {lang: {"faq": "nuevo", "process": "nuevo"} for lang in ("es", "en")},
        {lang: {} for lang in ("es", "en")},
    )
    assert len(changes) == 4


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("operation", ["save", "publish"])
@pytest.mark.parametrize("home", [True, False])
def test_real_concurrent_writers(operation, home):
    assert connection.vendor == "postgresql"
    sync_roles()
    user = User.objects.create_superuser(username="threads", email="threads@example.com")
    row = (
        HomeSection.objects.create(kind="statement", title_es="Antes")
        if home
        else Page.objects.get_or_create(
            kind="terms", defaults={"title_es": "Antes", "slug_es": "terms-threads"}
        )[0]
    )
    key = document_key(None if home else row)
    expected = version(key)
    barrier = Barrier(2)

    def run(index):
        close_old_connections()
        try:
            actor = User.objects.get(pk=user.pk)
            draft = type(row).objects.get(pk=row.pk)
            barrier.wait(timeout=10)
            if operation == "save":
                draft.title_es = f"Guardado {index}"
                try:
                    (services.save_section if home else services.save_page)(
                        draft, actor=actor, expected_version=expected
                    )
                    return "saved"
                except ContentConflict:
                    return "conflict"
            return (
                services.publish_home(actor, expected_version=expected)
                if home
                else services.publish_page(draft, actor, expected_version=expected)
            ).pk
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, (1, 2)))
    if operation == "save":
        assert sorted(results) == ["conflict", "saved"]
        assert version(key) == expected + 1
    else:
        assert results[0] == results[1]
        assert (HomePublication.objects if home else row.revisions).filter(
            pk=results[0]
        ).count() == 1


@pytest.mark.django_db(transaction=True)
def test_documents_migration_idempotent_safe_reverse():
    executor = MigrationExecutor(connection)
    leaves = executor.loader.graph.leaf_nodes()
    target = [("cms", "0014_alter_homesection_options_contentdocument_and_more")]
    try:
        executor.migrate(target)
        apps = executor.loader.project_state(target).apps
        page, _ = apps.get_model("cms", "Page").objects.get_or_create(
            kind="terms", defaults={"title_es": "Migración", "slug_es": "terms-migration"}
        )
        apps.get_model("cms", "ContentDocument").objects.filter(key=f"page:{page.kind}").delete()
        module = import_module("apps.cms.migrations.0015_content_documents")
        with connection.schema_editor() as editor:
            module.forwards(apps, editor)
            count = apps.get_model("cms", "ContentDocument").objects.count()
            module.forwards(apps, editor)
            module.backwards(apps, editor)
        assert apps.get_model("cms", "ContentDocument").objects.count() == count
        assert apps.get_model("cms", "ContentDocument").objects.filter(key="home").exists()
        for page in apps.get_model("cms", "Page").objects.all():
            assert (
                apps.get_model("cms", "ContentDocument")
                .objects.filter(key=f"page:{page.kind}")
                .exists()
            )
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(leaves)


def admin_payload(response):
    """Resubmit the actual admin form and all of its inline management forms."""
    forms = [response.context["adminform"].form]
    for inline in response.context["inline_admin_formsets"]:
        forms.extend([inline.formset.management_form, *inline.formset.forms])
    data = {"_continue": "1"}
    for form in forms:
        for name in form.fields:
            field = form[name]
            value = field.value()
            if value is not None and value is not False:
                data[field.html_name] = "on" if value is True else value
    return data


def test_page_and_multiple_inlines_share_one_version_and_keep_conflict_input(owner):
    browser, _user = owner
    page = Page.objects.get(kind="personalize")
    url = reverse("admin:cms_page_change", args=[page.pk])
    response = browser.get(url)
    data = admin_payload(response)
    expected = int(data["expected_version"])
    data.update(
        {
            "title_es": "Página cambiada",
            "process_steps-0-title_es": "Paso cambiado",
            "faq_items-0-question_es": "¿Pregunta cambiada?",
        }
    )
    assert browser.post(url, data).status_code == 302
    assert version(document_key(page)) == expected + 1
    page.refresh_from_db()
    assert page.process_steps.first().title_es == "Paso cambiado"
    assert page.faq_items.first().question_es == "¿Pregunta cambiada?"
    data["faq_items-0-question_es"] = "¿Mi texto sin perder?"
    response = browser.post(url, data)
    assert response.status_code == 200
    assert "Otra persona guardó cambios" in response.content.decode()
    inline = next(
        row
        for row in response.context["inline_admin_formsets"]
        if row.formset.prefix == "faq_items"
    )
    assert inline.formset.forms[0]["question_es"].value() == "¿Mi texto sin perder?"
    assert version(document_key(page)) == expected + 1


def test_review_stale_post_preserves_note_and_does_not_publish(owner):
    browser, user = owner
    page = Page.objects.get(kind="personalize")
    key = document_key(page)
    url = reverse("cms-review-publish", args=[key])
    first = publish(user, page)
    expected = browser.get(url).context["expected_version"]
    page.title_es = "Cambio posterior a la revisión"
    services.save_page(page, actor=user, expected_version=expected)
    response = browser.post(url, {"expected_version": expected, "note": "Mi nota conservada"})
    assert response.status_code == 409
    assert "El borrador cambió desde que lo revisaste" in response.content.decode()
    assert "Mi nota conservada" in response.content.decode()
    assert page.revisions.first().pk == first.pk


def test_preview_http_revocation_and_restore_http_permissions(owner):
    browser, user = staff(CONTENIDO)
    token = make_token(user)
    assert browser.get(reverse("cms-preview-verify"), {"token": token}).status_code == 200
    Group.objects.get(name=CONTENIDO).permissions.remove(
        Permission.objects.get(content_type__app_label="cms", codename="preview_content")
    )
    assert browser.get(reverse("cms-preview-verify"), {"token": token}).status_code == 403
    assert browser.get(reverse("admin:cms-home-preview")).status_code == 403
    page = Page.objects.get(kind="personalize")
    revision = page.revisions.first()
    restore_url = reverse("cms-history") + f"?document={page.pk}&restore={revision.pk}"
    assert (
        browser.post(
            restore_url, {"confirm": "yes", "expected_version": version(document_key(page))}
        ).status_code
        == 403
    )
    owner_browser, _owner_user = owner
    expected = version(document_key(page))
    assert (
        owner_browser.post(
            restore_url, {"confirm": "yes", "expected_version": expected}
        ).status_code
        == 302
    )
    assert (
        owner_browser.post(
            restore_url, {"confirm": "yes", "expected_version": expected}
        ).status_code
        == 409
    )


def test_document_update_failure_rolls_back_snapshot_and_pointer(owner):
    _, user = owner
    HomeSection.objects.all().delete()
    row = HomeSection.objects.create(kind="statement", title_es="Antes")
    first = publish(user)
    row.title_es = "Después"
    services.save_section(row, actor=user, expected_version=version())
    count = HomePublication.objects.count()
    with (
        patch.object(ContentDocument, "save", side_effect=RuntimeError("puntero fallido")),
        pytest.raises(RuntimeError),
    ):
        publish(user)
    assert HomePublication.objects.count() == count
    assert get_document("home").home_publication_id == first.pk
    assert selectors.home("es")["sections"][0]["title"] == "Antes"


def test_source_summary_includes_hidden_sections_original_languages_and_slide_order():
    from apps.cms.history import home_source_summary

    before = [
        {
            "id": 1,
            "title_es": "Oculta",
            "title_en": "Hidden",
            "is_visible": False,
            "slides": [{"id": 10}, {"id": 11}],
        }
    ]
    after = [
        {
            "id": 1,
            "title_es": "Otro título",
            "title_en": "Another title",
            "is_visible": False,
            "slides": [{"id": 11}, {"id": 10}],
        },
        {"id": 2, "title_es": "Nueva", "is_visible": False},
    ]
    changes = home_source_summary(after, before)
    for term in ["español", "inglés", "Fotos", "añadida (oculta)"]:
        assert any(term in change for change in changes)


@pytest.mark.parametrize("submitted", ["current", "stale", "missing"])
def test_home_changelist_sorting_is_versioned(owner, submitted):
    browser, actor = owner
    sections = [
        HomeSection.objects.create(kind="statement", title_es=f"Orden {i}") for i in range(2)
    ]
    url = reverse("admin:cms_homesection_changelist")
    formset = browser.get(url).context["cl"].formset
    expected = version()
    data = {"_save": "Guardar"}
    for key, value in formset.management_form.initial.items():
        data[f"{formset.prefix}-{key}"] = value
    for form in formset.forms:
        data[f"{form.prefix}-id"] = form.instance.pk
        data[f"{form.prefix}-position"] = form.instance.position + 10
        if submitted != "missing":
            data[f"{form.prefix}-expected_version"] = expected
    if submitted == "stale":
        services.save_section(sections[0], actor=actor, expected_version=expected)
    before = version()
    positions = dict(HomeSection.objects.values_list("pk", "position"))
    response = browser.post(url, data)
    if submitted == "current":
        assert response.status_code == 302
        assert version() == before + 1
        assert dict(HomeSection.objects.values_list("pk", "position")) == {
            pk: position + 10 for pk, position in positions.items()
        }
    else:
        assert response.status_code == 200
        assert response.context["cl"].formset.errors
        assert version() == before
        assert dict(HomeSection.objects.values_list("pk", "position")) == positions
