"""Contrato puro: estas pruebas no sustituyen la integración PostgreSQL."""

import json
import os
from copy import deepcopy
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError

from apps.cms.registry import (
    REGISTRY,
    export_registry,
    get_type,
    typescript_contract,
    validate_props,
)
from apps.cms.section_adapters import home_sections, localize_props, page_content


def bilingual(es="Texto", en="Text"):
    return {"es": es, "en": en}


def image():
    return {
        "src": "/media/cms/foto.webp",
        "srcset": "",
        "width": 1600,
        "height": 2000,
        "alt": bilingual("Piedra tallada", "Carved stone"),
    }


def props(kind):
    if kind == "image_text":
        return {"title": bilingual(), "body": bilingual(), "image": image()}
    if kind == "faq":
        return {"title": bilingual(), "items": [{"question": bilingual(), "answer": bilingual()}]}
    if kind == "process":
        return {"title": bilingual(), "steps": [{"title": bilingual()} for _ in range(2)]}
    return {}


def test_registry_typescript_is_current():
    root = Path(__file__).resolve().parents[4]
    target = root / "frontend/lib/api/sections.generated.ts"
    required = [target, target.with_name("types.ts"), target.with_name("section-registry.json")]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        reason = "Contrato frontend ausente: " + ", ".join(missing) + (
            "; monta frontend/lib/api en /frontend/lib/api o ejecuta npm test en frontend."
        )
        if os.environ.get("REQUIRE_FRONTEND_CONTRACT") == "1":
            pytest.fail(reason)
        pytest.skip(reason)
    assert json.loads(target.with_name("section-registry.json").read_text()) == json.loads(
        json.dumps(export_registry())
    ), "Regenera con export_section_registry"
    assert target.read_text() == typescript_contract(), (
        "Regenera con export_section_registry --typescript"
    )
    source = (root / "frontend/lib/api/types.ts").read_text()
    assert "export type { Section } from './sections.generated'" in source


def test_registry_metadata_and_openapi_fields():
    from apps.cms.api.serializers import SECTION_SERIALIZERS

    assert len(REGISTRY) == 11
    assert set(SECTION_SERIALIZERS) == set(REGISTRY)
    for spec in REGISTRY.values():
        assert spec.name and spec.description and spec.icon and spec.documents
        assert spec.schema_version == 1
        expected = {"id", "kind", "schema_version"} | {
            key.rstrip("?") for key, _ in spec.public_fields
        }
        assert set(SECTION_SERIALIZERS[spec.kind]().fields) == expected
        for slot in spec.slots:
            assert slot.alt_required == ("es", "en") and slot.desktop and slot.mobile
    assert any(f.key == "subtitle" for f in REGISTRY["category_grid"].fields)
    assert export_registry()["locales"] == ["es", "en"]


@pytest.mark.parametrize("kind", list(REGISTRY))
def test_unknown_fields_rejected_for_every_type(kind):
    with pytest.raises(ValidationError) as error:
        validate_props(kind, {"css": "body {display:none}"})
    assert "css" in error.value.message_dict


@pytest.mark.parametrize("kind", ["image_text", "faq", "process"])
def test_new_types_defaults_and_translations(kind):
    result = validate_props(kind, props(kind))
    for locale in ("es", "en"):
        rendered = localize_props(kind, result, locale)
        assert rendered["title"] == ("Texto" if locale == "es" else "Text")
    broken = props(kind)
    broken["title"] = {"es": "Título"}
    with pytest.raises(ValidationError) as error:
        validate_props(kind, broken)
    assert "title.en" in error.value.message_dict
    broken["title"] = bilingual("a" * 301)
    with pytest.raises(ValidationError):
        validate_props(kind, broken)


@pytest.mark.parametrize(
    ("kind", "field", "count"),
    [("faq", "items", 21), ("process", "steps", 1), ("process", "steps", 9)],
)
def test_item_limits(kind, field, count):
    value = props(kind)
    value[field] = value[field][:1] * count
    with pytest.raises(ValidationError) as error:
        validate_props(kind, value)
    assert field in error.value.message_dict


def test_nested_errors_and_markdown_are_safe():
    value = props("faq")
    value["items"][0]["answer"] = bilingual(
        "[Bien](/es/legal/devoluciones) [Mal](javascript:alert(1)) <script>alert(1)</script>"
    )
    public = localize_props("faq", validate_props("faq", value), "es")
    html = public["items"][0]["answer_html"]
    assert 'href="/es/legal/devoluciones"' in html
    assert "<script>" not in html and 'href="javascript:' not in html
    value["items"][0]["question"] = {"es": "Pregunta"}
    with pytest.raises(ValidationError) as error:
        validate_props("faq", value)
    assert "items.0.question.en" in error.value.message_dict


@pytest.mark.parametrize("kind", ["catalog", "personalize", "story", "contact", "external"])
def test_typed_cta(kind):
    value = props("image_text")
    value["cta"] = {"kind": kind, "label": bilingual("Ver", "View")}
    if kind == "external":
        value["cta"]["url"] = "https://example.com/path"
    assert validate_props("image_text", value)["cta"] == value["cta"]
    value["cta"]["css"] = "evil"
    with pytest.raises(ValidationError):
        validate_props("image_text", value)


@pytest.mark.parametrize(
    "url", ["http://example.com", "//example.com", "javascript:alert(1)", "/es/no-existe"]
)
def test_cta_unsafe_destinations(url):
    value = props("image_text")
    value["cta"] = {"kind": "external", "label": bilingual(), "url": url}
    with pytest.raises(ValidationError):
        validate_props("image_text", value)


@pytest.mark.parametrize("key", ["image", "mobile_image"])
@pytest.mark.parametrize("locale", ["es", "en"])
def test_all_image_slots_need_alt(key, locale):
    value = props("image_text")
    value[key] = image()
    value[key]["alt"].pop(locale)
    with pytest.raises(ValidationError):
        validate_props("image_text", value)


@pytest.mark.parametrize(
    ("kind", "version", "document"),
    [
        ("alien", 1, "home"),
        ("hero", 2, "home"),
        ("hero", True, "home"),
        ("hero", 1, "page:personalize"),
    ],
)
def test_unknown_type_version_and_document(kind, version, document):
    with pytest.raises(ValidationError):
        get_type(kind, version, document)


def test_adapters_do_not_mutate_and_omit_unknown(caplog):
    rows = [
        {
            "kind": "hero",
            "title": "Título",
            "slides": [{"image": image(), "mobile_image": image()}],
        },
        {"kind": "future"},
        {"kind": "hero", "schema_version": 9},
    ]
    original = deepcopy(rows)
    result = home_sections(rows)
    assert len(result) == 1 and result[0]["schema_version"] == 1
    assert rows == original and "desconocida" in caplog.text
    old = {"es": {"title": "Título"}, "en": {"title": "Title"}}
    assert page_content(old) == old


@pytest.mark.parametrize("kind", ["hero", "story", "personalize", "banner", "image_text"])
@pytest.mark.parametrize("locale", ["es", "en"])
def test_legacy_and_new_image_alt_contract(kind, locale):
    value = props(kind)
    value["image"] = image()
    value["image"]["alt"].pop(locale)
    with pytest.raises(ValidationError) as error:
        validate_props(kind, value)
    assert f"image.alt.{locale}" in error.value.message_dict


@pytest.mark.parametrize("locale", ["es", "en"])
def test_hero_slide_alt_contract(locale):
    value = {"slides": [{"device": "mobile", "image": image()}]}
    value["slides"][0]["image"]["alt"].pop(locale)
    with pytest.raises(ValidationError) as error:
        validate_props("hero", value)
    assert f"slides.0.image.alt.{locale}" in error.value.message_dict


@pytest.mark.parametrize("kind", ["image_text", "faq", "process"])
def test_new_model_validation_renderer_and_openapi_without_database(kind):
    from drf_spectacular.generators import SchemaGenerator

    from apps.cms.models import HomeSection
    from apps.cms.selectors import render_sections
    from apps.cms.services import validate_section
    from apps.cms.tests.test_phase3 import assert_openapi

    obj = HomeSection(kind=kind, props=props(kind))
    validate_section(obj)
    obj.pk = 1
    schema = SchemaGenerator().get_schema(request=None, public=True)
    for locale in ("es", "en"):
        actual = {"sections": render_sections([obj], locale), "published_at": None, "preview": True}
        assert_openapi(
            actual, schema["components"]["schemas"]["Home"], schema["components"]["schemas"]
        )


def test_readable_bilingual_props_summary_and_audit_removals():
    from unittest.mock import patch

    from apps.cms.history import home_source_summary
    from apps.cms.models import HomeSection
    from apps.cms.registry import editorial_props
    from apps.cms.services import audit_editorial

    old = validate_props("process", props("process"))
    new = deepcopy(old)
    new["steps"][0]["title"]["en"] = "New first step"
    before = {"id": 1, "kind": "process", "props": old}
    after = {"id": 1, "kind": "process", "props": new}
    changes = home_source_summary([after], [before])
    assert any("inglés" in item for item in changes)
    assert not any("español" in item for item in changes)
    new["steps"].pop()
    obj = HomeSection(kind="process", props=new)
    with patch("apps.cms.services.record") as record:
        audit_editorial(obj, editorial_props("process", old))
    diff = record.call_args.kwargs["diff"]
    assert diff["Pasos 2 · Paso (español)"] == ["Texto", ""]
    assert not any("{" in str(value) for value in diff.values())


@pytest.mark.parametrize("kind", ["hero", "story", "personalize", "banner", "image_text"])
def test_column_image_replacement_audit_survives_registry_labels(kind):
    from unittest.mock import patch

    from apps.cms.models import HomeSection
    from apps.cms.services import audit_editorial, editorial_values

    obj = HomeSection(kind=kind, image="cms/old.webp")
    before = editorial_values(obj)
    assert before["Imagen"] == "Foto cargada"
    obj.image = "cms/new.webp"
    with patch("apps.cms.services.record") as record:
        audit_editorial(obj, before, image_changed=True)
    assert record.call_args.kwargs["diff"]["Foto"] == ["Foto anterior", "Foto reemplazada"]


@pytest.mark.parametrize("required", [False, True])
def test_missing_frontend_contract_has_explicit_policy(monkeypatch, required):
    monkeypatch.setenv("REQUIRE_FRONTEND_CONTRACT", "1" if required else "0")
    monkeypatch.setattr(Path, "is_file", lambda self: False)
    expected = pytest.fail.Exception if required else pytest.skip.Exception
    with pytest.raises(expected, match="Contrato frontend ausente"):
        test_registry_typescript_is_current()
