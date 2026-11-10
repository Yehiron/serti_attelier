"""Adaptadores puros de lectura: nunca actualizan publicaciones inmutables."""

import logging
from copy import deepcopy

from .registry import REGISTRY

logger = logging.getLogger(__name__)


def home_sections(rows):
    result = []
    for row in deepcopy(rows):
        spec = REGISTRY.get(row.get("kind"))
        if not spec or row.get("schema_version", 1) != spec.schema_version:
            logger.warning(
                "Se omite una sección CMS desconocida: %s v%s",
                row.get("kind"),
                row.get("schema_version", 1),
            )
            continue
        row.setdefault("schema_version", 1)
        result.append(row)
    return result


def page_content(snapshot):
    result = deepcopy(snapshot)
    for locale in ("es", "en"):
        for key in ("process", "faq"):
            if key in result[locale]:
                result[locale][key].setdefault("schema_version", 1)
    return result


def section_sources(rows):
    result = deepcopy(rows)
    for row in result:
        row.setdefault("schema_version", 1)
        row.setdefault("props", {})
    return result


def home_snapshot(snapshot):
    return {locale: home_sections(snapshot[locale]) for locale in ("es", "en")}


def localize_props(kind, props, locale):
    from apps.catalog.models import Category, Collection, Piece, Stone
    from apps.core.routes import href

    from .models import Page
    from .services import render_markdown

    def localize(fields, values):
        result = {}
        for field in fields:
            value = values.get(field.key, field.default)
            if field.translated:
                value = value.get(locale, "") or value.get("es", "")
            if field.type == "list":
                value = [localize(field.fields, row) for row in value]
            if field.type == "markdown":
                result[field.key + "_html"] = render_markdown(value)
                continue
            if field.type == "image" and value:
                if "asset" in value:
                    from .media import resolve

                    value = resolve(value, locale)
                else:
                    value = deepcopy(value)
                    value["alt"] = value["alt"].get(locale) or value["alt"]["es"]
            if field.type == "cta" and value:
                target = None
                if value["kind"] in {"category", "collection", "piece", "stone", "page"}:
                    model = {
                        "category": Category,
                        "collection": Collection,
                        "piece": Piece,
                        "stone": Stone,
                        "page": Page,
                    }[value["kind"]]
                    target = model.objects.filter(pk=value["target"]).first()
                    if target is None:
                        result[field.key] = None
                        continue
                value = {
                    "label": value["label"].get(locale) or value["label"]["es"],
                    "href": value["url"]
                    if value["kind"] == "external"
                    else href(value["kind"], locale, target),
                    "external": value["kind"] == "external",
                }
            result[field.key] = value
        return result

    return localize(REGISTRY[kind].fields, props)
