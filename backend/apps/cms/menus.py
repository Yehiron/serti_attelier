"""Fixed menu documents reuse document versions, review and immutable publications."""

from copy import deepcopy

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.audit.services import record
from apps.core.routes import href

from .documents import check_version, lock_document, require_capability
from .models import ContentDocument, DraftRevision, MenuPublication, Page
from .page_options import draft_path, snapshot_path
from .registry import validate_cta

MENU_KEYS = {"menu:main", "menu:footer"}


def validate_items(key, items, *, publishing=False):
    if (
        key not in MENU_KEYS
        or not isinstance(items, list)
        or len(items) > (8 if key == "menu:main" else 12)
    ):
        raise ValidationError("Usa como máximo 8 enlaces principales o 12 en el pie de página.")
    for item in items:
        if (
            not isinstance(item, dict)
            or set(item) != {"link", "visible"}
            or type(item["visible"]) is not bool
        ):
            raise ValidationError("Revisa los enlaces del menú.")
        link = item["link"]
        if not isinstance(link, dict):
            raise ValidationError("Elige un destino para cada enlace.")
        labels = link.get("label", {})
        if (
            not isinstance(labels, dict)
            or set(labels) != {"es", "en"}
            or any(not isinstance(s, str) or len(s) > 40 for s in labels.values())
            or not labels.get("es", "").strip()
        ):
            raise ValidationError("Escribe etiquetas de hasta 40 caracteres en español e inglés.")
        kind = link.get("kind")
        if kind == "external" and key != "menu:footer":
            raise ValidationError("Los enlaces externos solo se permiten en el pie de página.")
        if kind in {"stones", "collections", "home"}:
            if set(link) != {"kind", "label"} or (kind != "home" and key != "menu:main"):
                raise ValidationError("Selecciona un destino válido para este menú.")
        elif kind == "page":
            if (
                set(link) != {"kind", "label", "target"}
                or type(link["target"]) is not int
                or not Page.objects.filter(pk=link["target"]).exists()
            ):
                raise ValidationError("Selecciona una página existente.")
            if (
                publishing
                and not Page.objects.filter(
                    pk=link["target"], status="published", version__gt=0
                ).exists()
            ):
                raise ValidationError("Publica primero la página elegida como destino del menú.")
        elif kind == "piece":
            raise ValidationError("Elige una página, categoría, colección, piedra o catálogo.")
        else:
            validate_cta(
                {**link, "label": {"es": labels["es"], "en": labels["en"] or labels["es"]}}
            )
    return deepcopy(items)


def menu_groups(current, previous):
    from .review_changes import equivalent

    if equivalent(current, previous):
        return []

    def text(rows):
        labels = []
        for index, row in enumerate(rows):
            link = row["link"]
            target = link.get("target") or link.get("url") or ""
            state = "visible" if row["visible"] else "oculto"
            labels.append(
                f"{index + 1}. {link['label']['es']} / {link['label']['en']} "
                f"({state}; {link['kind']}{': ' + str(target) if target else ''})"
            )
        return " · ".join(labels) or "Sin enlaces"

    return [
        {
            "name": "Enlaces del menú",
            "icon": "menu",
            "rows": [
                {
                    "label": "Orden, etiquetas y destinos",
                    "before": text(previous),
                    "after": text(current),
                }
            ],
        }
    ]


@transaction.atomic
def publish_menu(key, actor, request=None, note="", *, expected_version=None):
    require_capability(actor, "publish")
    document = lock_document(key)
    check_version(document, expected_version, publishing=True)
    if len(note) > 300:
        raise ValidationError("La nota puede tener hasta 300 caracteres.")
    items = validate_items(key, document.menu_items, publishing=True)
    latest = document.menu_publication
    if not latest or latest.snapshot != items:
        latest = MenuPublication.objects.create(
            menu=key[5:],
            snapshot=items,
            note=note,
            published_by=actor,
            published_by_repr=actor.get_username(),
        )
        record("cms.menu_published", actor=actor, obj=latest, request=request)
    document.menu_publication = latest
    document.published_version = document.draft_version
    document.save(update_fields=["menu_publication", "published_version"])
    return latest


@transaction.atomic
def restore_menu(publication, actor, request=None, *, expected_version=None):
    require_capability(actor, "restore")
    document = lock_document("menu:" + publication.menu)
    check_version(document, expected_version)
    document.menu_items = validate_items(document.key, publication.snapshot)
    document.draft_version += 1
    document.updated_by = actor
    document.save(update_fields=["menu_items", "draft_version", "updated_by", "updated_at"])
    DraftRevision.objects.create(
        document=document,
        draft_version=document.draft_version,
        snapshot=deepcopy(document.menu_items),
        restored_from_menu=publication,
        published_by=actor,
        published_by_repr=actor.get_username(),
    )
    record("cms.menu_restored", actor=actor, obj=publication, request=request)


def public_menu(key, locale, preview=False):
    from apps.catalog.models import Category, Collection, Stone

    document = ContentDocument.objects.select_related("menu_publication").filter(key=key).first()
    items = (
        document.menu_items
        if document and preview
        else document.menu_publication.snapshot
        if document and document.menu_publication
        else []
    )
    pages = {p.pk: p for p in Page.objects.prefetch_related("revisions")}
    taxonomies = {}
    for kind, model in (("category", Category), ("collection", Collection), ("stone", Stone)):
        ids = {r["link"]["target"] for r in items if r["link"]["kind"] == kind}
        taxonomies[kind] = {row.pk: row for row in model.objects.filter(pk__in=ids)} if ids else {}
    result = []
    for row in items:
        if not row["visible"]:
            continue
        link = row["link"]
        kind = link["kind"]
        dropdown = (
            kind if key == "menu:main" and kind in {"catalog", "stones", "collections"} else None
        )
        if kind == "external":
            url = link["url"]
        elif kind in {"page", "personalize", "story", "contact"}:
            page = (
                pages.get(link.get("target"))
                if kind == "page"
                else next(
                    (
                        p
                        for p in pages.values()
                        if p.kind == {"story": "manufacturer"}.get(kind, kind)
                    ),
                    None,
                )
            )
            revision = next(iter(page.revisions.all()), None) if page else None
            if not page or (not preview and not revision):
                if kind == "page":
                    continue
                url = href(kind, locale)
            else:
                url = (
                    draft_path(page, locale)
                    if preview
                    else snapshot_path(page, revision.snapshot, locale)
                )
        elif kind in taxonomies:
            target = taxonomies[kind].get(link["target"])
            if not target:
                continue
            url = href(kind, locale, target)
        else:
            url = href("catalog" if kind in {"stones", "collections"} else kind, locale)
        if not url:
            continue
        result.append(
            {
                "label": link["label"].get(locale) or link["label"]["es"],
                "href": url,
                "external": kind == "external",
                "dropdown": dropdown,
            }
        )
    return {"items": result, "preview": preview}
