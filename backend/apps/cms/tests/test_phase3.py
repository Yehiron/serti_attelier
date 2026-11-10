"""Pruebas de integración: PostgreSQL real, servicios versionados y snapshots."""

import json
from copy import deepcopy
from importlib import import_module
from pathlib import Path

import pytest
from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, RequestFactory
from django.urls import reverse
from drf_spectacular.generators import SchemaGenerator
from rest_framework.renderers import JSONRenderer

from apps.cms import selectors, services
from apps.cms.admin import HomeSectionAdmin
from apps.cms.documents import ContentConflict, get_document
from apps.cms.models import DraftRevision, HomePublication, HomeSection, Page, PageRevision
from apps.cms.registry import REGISTRY, validate_props
from apps.cms.section_adapters import home_sections, page_content
from apps.cms.tests.helpers import historical_public_bytes
from apps.cms.tests.test_registry import bilingual, props

pytestmark = pytest.mark.django_db
FIXTURES = Path(__file__).with_name("fixtures")


def version(key="home"):
    return get_document(key).draft_version


@pytest.mark.parametrize("kind", list(REGISTRY))
def test_every_type_validates_and_saves(kind, cms_actor):
    from apps.catalog.models import Collection

    values = props(kind)
    if kind == "collection_rail":
        collection = Collection.objects.first() or Collection.objects.create(
            name_es="Colección", slug_es="prueba"
        )
        values["collection"] = collection.pk
    validated = validate_props(kind, values)
    if REGISTRY[kind].storage == "columns":
        obj = HomeSection(kind=kind)
        if kind == "collection_rail":
            obj.collection_id = validated["collection"]
    else:
        obj = HomeSection(kind=kind, props=values)
    services.save_section(obj, actor=cms_actor, expected_version=version())
    obj.refresh_from_db()
    assert obj.schema_version == 1


@pytest.mark.parametrize("kind", ["image_text", "faq", "process"])
def test_save_publish_restore_both_languages(kind, cms_actor):
    HomeSection.objects.all().delete()
    obj = HomeSection(kind=kind, props=props(kind))
    before = version()
    services.save_section(obj, actor=cms_actor, expected_version=before)
    assert version() == before + 1
    with pytest.raises(ContentConflict):
        services.save_section(obj, actor=cms_actor, expected_version=before)
    with pytest.raises(PermissionDenied):
        services.save_section(obj, expected_version=version())
    publication = services.publish_home(cms_actor, expected_version=version())
    original = deepcopy(publication.snapshot)
    for locale, title in [("es", "Texto"), ("en", "Text")]:
        data = Client().get(reverse("cms-home"), {"locale": locale}).json()["sections"][0]
        assert data["title"] == title and data["schema_version"] == 1
        assert data["kind"] == kind
    obj.props["title"] = bilingual("Otro", "Other")
    services.save_section(obj, actor=cms_actor, expected_version=version())
    assert selectors.home("es")["sections"][0]["title"] == "Texto"
    services.restore_home(publication, cms_actor, expected_version=version())
    assert HomeSection.objects.get(pk=obj.pk).props["title"] == bilingual()
    restore = DraftRevision.objects.filter(document__key="home").first()
    assert restore.restored_from == publication
    assert restore.snapshot[0]["props"]["title"] == bilingual()
    assert services.publish_home(cms_actor, expected_version=version()).pk == publication.pk
    publication.refresh_from_db()
    assert publication.snapshot == original


@pytest.mark.parametrize(
    ("field", "value"),
    [("kind", "future"), ("schema_version", 99), ("props", {"title": {"es": "Incompleto"}})],
)
def test_save_rejects_bad_kind_version_props_without_version_bump(field, value, cms_actor):
    obj = HomeSection(kind="image_text", props=props("image_text"))
    setattr(obj, field, value)
    before = version()
    with pytest.raises(ValidationError):
        services.save_section(obj, actor=cms_actor, expected_version=before)
    assert version() == before
    assert obj.pk is None


def test_irrelevant_columns_and_props_are_rejected(cms_actor):
    for obj in (
        HomeSection(kind="statement", subtitle_es="No corresponde"),
        HomeSection(kind="hero", props={"css": "display:none"}),
    ):
        with pytest.raises(ValidationError):
            services.save_section(obj, actor=cms_actor, expected_version=version())


@pytest.mark.parametrize("kind", ["category", "collection", "piece", "stone", "page"])
def test_cta_reference_must_exist(kind):
    values = props("image_text")
    values["cta"] = {"kind": kind, "label": bilingual(), "target": 999999999}
    with pytest.raises(ValidationError):
        validate_props("image_text", values)


def test_internal_cta_localization_and_legal_restriction():
    page = Page.objects.get(kind="returns")
    values = props("image_text")
    values["cta"] = {"kind": "page", "label": bilingual(), "target": page.pk}
    from apps.cms.section_adapters import localize_props

    for lang in ("es", "en"):
        rendered = localize_props("image_text", validate_props("image_text", values), lang)
        assert rendered["cta"]["href"].startswith("/" + lang + "/legal/")
    values["cta"]["target"] = Page.objects.get(kind="contact").pk
    with pytest.raises(ValidationError):
        validate_props("image_text", values)


def test_registry_endpoint_is_admin_authenticated_and_read_only(cms_actor):
    client = Client()
    url = reverse("cms-section-registry")
    assert client.get(url).status_code in (302, 403)
    # RequestFactory bypasses only the admin OTP wrapper, not the view permission.
    from apps.cms.registry_view import section_registry

    request = RequestFactory().get(url)
    request.user = cms_actor
    response = section_registry(request)
    assert len(json.loads(response.content)["sections"]) == 11
    assert response["Cache-Control"] == "private, no-store"
    assert section_registry(RequestFactory().post(url)).status_code == 405
    cms_actor.is_superuser = False
    cms_actor.save()
    with pytest.raises(PermissionDenied):
        section_registry(request)


def test_unfold_visible_fields_come_from_registry(cms_actor):
    request = RequestFactory().get("/")
    request.user = cms_actor
    model_admin = HomeSectionAdmin(HomeSection, admin.site)
    for kind in REGISTRY:
        fieldsets = str(model_admin.get_fieldsets(request, HomeSection(kind=kind)))
        if REGISTRY[kind].storage != "columns":
            assert "props" in fieldsets and "body_es" not in fieldsets
        if kind == "category_grid":
            assert "subtitle" in fieldsets and "cta_kind" not in fieldsets


def assert_openapi(value, schema, components):
    """Validate actual response structure, required fields, enums and discriminators.

    Small local OpenAPI 3 checker avoids introducing a dependency in this phase.
    """
    if "$ref" in schema:
        return assert_openapi(value, components[schema["$ref"].split("/")[-1]], components)
    if value is None and schema.get("nullable"):
        return
    if "oneOf" in schema:
        discriminator = schema.get("discriminator")
        if discriminator:
            ref = discriminator["mapping"][value[discriminator["propertyName"]]]
            return assert_openapi(value, {"$ref": ref}, components)
        for choice in schema["oneOf"]:
            try:
                assert_openapi(value, choice, components)
                return
            except (AssertionError, KeyError):
                continue
        raise AssertionError("Ninguna variante OpenAPI coincide")
    for part in schema.get("allOf", []):
        assert_openapi(value, part, components)
    if "enum" in schema:
        assert value in schema["enum"]
    kind = schema.get("type")
    if kind == "object":
        assert isinstance(value, dict)
        assert set(schema.get("required", [])) <= value.keys()
        properties = schema.get("properties", {})
        assert value.keys() <= properties.keys()
        for key, item in value.items():
            assert_openapi(item, properties[key], components)
    elif kind == "array":
        assert isinstance(value, list)
        for row in value:
            assert_openapi(row, schema["items"], components)
    elif kind == "string":
        assert isinstance(value, str)
    elif kind == "integer":
        assert type(value) is int
    elif kind == "boolean":
        assert type(value) is bool


def test_real_home_and_pages_match_openapi(cms_actor):
    HomeSection.objects.all().delete()
    for index, kind in enumerate(("image_text", "faq", "process", "category_grid", "hero")):
        obj = HomeSection(
            kind=kind,
            position=index,
            props=props(kind) if kind in ("image_text", "faq", "process") else {},
        )
        services.save_section(obj, actor=cms_actor, expected_version=version())
    services.publish_home(cms_actor, expected_version=version())
    page = Page.objects.get(kind="personalize")
    services.publish_page(page, cms_actor, expected_version=version("page:personalize"))
    schema = SchemaGenerator().get_schema(request=None, public=True)
    for locale in ("es", "en"):
        for endpoint, path in [
            ("cms-home", "/api/v1/cms/home"),
            ("cms-page-kind", "/api/v1/cms/pages/kind/{kind}"),
        ]:
            url = reverse(
                endpoint, kwargs={"kind": "personalize"} if endpoint == "cms-page-kind" else {}
            )
            response = Client().get(url, {"locale": locale})
            assert response.status_code == 200
            contract = schema["paths"][path]["get"]["responses"]["200"]["content"][
                "application/json"
            ]["schema"]
            assert_openapi(response.json(), contract, schema["components"]["schemas"])


def test_legacy_snapshots_public_payload_and_unknown_type():
    snapshot = json.loads((FIXTURES / "home_legacy_paired.json").read_text())
    snapshot["es"].append({"id": 100, "kind": "future"})
    publication = HomePublication.objects.create(snapshot=snapshot)
    for locale in ("es", "en"):
        response = Client().get(reverse("cms-home"), {"locale": locale})
        assert response.status_code == 200
        assert len(response.json()["sections"]) == 8
        assert response.json()["sections"][0]["slides"][0]["mobile_image"]
    publication.refresh_from_db()
    assert publication.snapshot == snapshot
    page = Page.objects.get(kind="personalize")
    old = json.loads((FIXTURES / "page_phase1.json").read_text())
    revision = PageRevision.objects.create(page=page, version=page.version + 1, snapshot=old)
    for locale in ("es", "en"):
        payload = selectors.page_payload(page, locale, revision)
        assert payload["process"]["schema_version"] == 1
        assert (
            payload["process"]["steps"][0]["title"] == old[locale]["process"]["steps"][0]["title"]
        )
    revision.refresh_from_db()
    assert revision.snapshot == old


def strip_schema(value):
    if isinstance(value, dict):
        return {key: strip_schema(item) for key, item in value.items() if key != "schema_version"}
    if isinstance(value, list):
        return [strip_schema(item) for item in value]
    return value


@pytest.mark.django_db(transaction=True)
def test_migration_preserves_public_bytes_idempotent_and_safe_reverse():
    before = [("cms", "0016_alter_contentdocument_options_and_more")]
    after = [("cms", "0018_registry_defaults")]
    executor = MigrationExecutor(connection)
    executor.migrate(before)
    try:
        historical = executor.loader.project_state(before).apps
        section_model = historical.get_model("cms", "HomeSection")
        # Frozen fixture shapes and copy come from migrations 0002/0013, not personal data.
        home_snapshot = json.loads((FIXTURES / "home_legacy_paired.json").read_text())
        historical.get_model("cms", "HomePublication").objects.create(snapshot=home_snapshot)
        page, _ = historical.get_model("cms", "Page").objects.get_or_create(
            kind="personalize",
            defaults={"title_es": "Personaliza", "slug_es": "personaliza", "slug_en": "customize"},
        )
        section_model.objects.get_or_create(kind="statement", defaults={"title_es": "SERTI"})
        old_page = json.loads((FIXTURES / "page_phase1.json").read_text())
        revision = historical.get_model("cms", "PageRevision").objects.create(
            page_id=page.pk, version=page.version + 1, snapshot=old_page
        )
        page.version, page.status = revision.version, "published"
        page.save()
        sources = list(section_model.objects.values())
        # Real public views read historical models while their schema is under expansion.
        urls = [reverse("cms-home"), reverse("cms-page-kind", args=["personalize"])]
        baseline = {
            (url, locale): historical_public_bytes(historical, url, locale)
            for url in urls
            for locale in ("es", "en")
        }
        executor = MigrationExecutor(connection)
        executor.migrate(after)
        current = executor.loader.project_state(after).apps
        normalization = import_module("apps.cms.migrations.0018_registry_defaults")
        with connection.schema_editor() as editor:
            normalization.normalize(current, editor)
            normalization.normalize(current, editor)
        assert all(
            row.schema_version == 1 and row.props == {}
            for row in current.get_model("cms", "HomeSection").objects.all()
        )
        for url in urls:
            for locale in ("es", "en"):
                assert historical_public_bytes(current, url, locale) == baseline[url, locale]
        # Compare with the historical model: the runtime model's modeltranslation manager
        # rewrites `title` to `title_<active language>`, which depends on earlier tests.
        assert (
            list(current.get_model("cms", "HomeSection").objects.values(*sources[0].keys()))
            == sources
        )
        # Baseline adapters add schema_version; excluding that one additive field,
        # the frozen historical content also remains byte-identical.
        for locale in ("es", "en"):
            assert JSONRenderer().render(
                strip_schema(home_sections(home_snapshot[locale]))
            ) == JSONRenderer().render(home_snapshot[locale])
            assert strip_schema(page_content(old_page)) == old_page
        executor.migrate(
            before
        )  # data reverse is non-destructive; schema contraction only on old types
        assert section_model.objects.count() == len(sources)
    finally:
        latest = MigrationExecutor(connection)
        latest.migrate(latest.loader.graph.leaf_nodes())


def test_schema_reverse_refuses_to_discard_new_content(cms_actor):
    from django.apps import apps
    from django.db.migrations.exceptions import IrreversibleError

    module = import_module(
        "apps.cms.migrations.0017_homesection_props_homesection_schema_version_and_more"
    )
    obj = HomeSection(kind="image_text", props=props("image_text"))
    services.save_section(obj, actor=cms_actor, expected_version=version())
    with pytest.raises(IrreversibleError):
        module.guard_schema_reverse(apps, connection.schema_editor())
    obj.refresh_from_db()
    assert obj.props["title"] == bilingual()
