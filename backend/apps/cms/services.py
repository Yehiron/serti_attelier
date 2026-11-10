from __future__ import annotations

import html
import uuid
from copy import deepcopy
from string import Formatter
from typing import Any

import markdown  # type: ignore[import-untyped]
import nh3
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.audit.services import record
from apps.catalog.images import (
    build_renditions,
    cap_master,
    crop_to_ratio,
    encode_webp,
    validated_image,
)

from .documents import (
    check_version,
    document_key,
    draft_mutation,
    lock_document,
    require_capability,
)
from .models import (
    DraftRevision,
    FaqItem,
    HeroSlide,
    HomePublication,
    HomeSection,
    Page,
    PageRevision,
    PersonalizationService,
    ProcessStep,
)

TAGS = {
    "p",
    "h2",
    "h3",
    "h4",
    "ul",
    "ol",
    "li",
    "strong",
    "em",
    "a",
    "blockquote",
    "hr",
    "br",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
}


def render_markdown(source: str) -> str:
    # Escape raw HTML before Markdown parsing; authored HTML is never executable.
    rendered = markdown.markdown(
        html.escape(source, quote=False), extensions=["extra", "sane_lists"]
    )
    return str(
        nh3.clean(
            rendered,
            tags=TAGS,
            attributes={"a": {"href", "title"}},
            url_schemes={"https", "mailto"},
            link_rel="noopener noreferrer",
            attribute_filter=_safe_attribute,
        )
    )


def _safe_attribute(tag: str, attribute: str, value: str) -> str | None:
    # Protocol-relative URLs are external and are not part of the relative-link contract.
    if attribute == "href" and value.strip().startswith(("//", "\\")):
        return None
    return value


def require_publish(actor: User | AnonymousUser) -> User:
    if not actor.is_active or not actor.is_staff or not actor.has_perm("cms.publish_content"):
        raise PermissionDenied
    if not isinstance(actor, User):
        raise PermissionDenied
    return actor


def validate_section(obj: HomeSection) -> None:
    if obj.image_reference:
        from .media import validate_reference

        validate_reference(obj.image_reference)
    from .section_validation import reject_irrelevant_columns, validate_instance

    reject_irrelevant_columns(obj)
    validate_instance(obj)
    obj.full_clean()
    if obj.kind == "collection_rail" and not obj.collection_id:
        raise ValidationError(_("Selecciona una colección para esta sección."))
    if obj.cta_kind in {"category", "stone", "collection", "piece", "page"} and not getattr(
        obj, f"cta_{obj.cta_kind}_id"
    ):
        raise ValidationError(_("Selecciona el destino del enlace."))
    if (
        obj.cta_kind == "page"
        and obj.cta_page
        and obj.cta_page.kind not in {"terms", "privacy", "returns", "shipping", "cookies"}
    ):
        raise ValidationError(_("Selecciona una página legal."))
    if obj.cta_kind == "external" and not obj.cta_external_url:
        raise ValidationError(_("Escribe un enlace HTTPS."))
    if obj.cta_kind != "none" and not obj.cta_label:
        raise ValidationError(_("Escribe el texto del enlace."))
    if obj.image and not obj.image_reference:
        for locale in ("es", "en"):
            if not getattr(obj, f"image_alt_{locale}", ""):
                raise ValidationError(_("Escribe el texto alternativo en español e inglés."))


def display_ratio(obj: HomeSection | PersonalizationService) -> tuple[int, int] | None:
    """Crop ratio matching how the site shows the image: full-bleed hero 16:9, editorial
    photos and personalization services in a 4:5 portrait frame."""
    if isinstance(obj, PersonalizationService) or obj.kind in {"story", "personalize", "banner"}:
        return (4, 5)
    if obj.kind == "hero":
        return (16, 9)
    return None


def process_image(obj: HomeSection | PersonalizationService, actor=None, request=None) -> None:
    if not obj.image:
        _library_changed_alt(obj, actor)
        obj.renditions, obj.width, obj.height = {}, 0, 0
        return
    if getattr(obj.image, "_committed", True):
        _library_changed_alt(obj, actor)
        return
    asset = _library_original(obj.image, actor, request)
    obj.image_reference = {}
    image = validated_image(obj.image)
    if ratio := display_ratio(obj):
        image = crop_to_ratio(image, *ratio)
    image = cap_master(image)
    obj.width, obj.height = image.size
    obj.image.save(f"{uuid.uuid4().hex}.webp", encode_webp(image), save=False)
    paths = build_renditions(image, f"cms/renditions/{uuid.uuid4().hex}", (960, 1600, 2400))
    obj.renditions = {"webp": paths}
    _library_processed(obj, asset)


def process_slide_images(obj: HeroSlide, actor=None, request=None) -> None:
    if not obj.image or getattr(obj.image, "_committed", True):
        _library_changed_alt(obj, actor)
        return
    asset = _library_original(obj.image, actor, request)
    obj.image_reference = {}
    image = cap_master(validated_image(obj.image))
    widths = (480, 960, 1600) if obj.device == HeroSlide.Device.MOBILE else (960, 1600, 2400)
    obj.width, obj.height = image.size
    obj.image.save(f"{uuid.uuid4().hex}.webp", encode_webp(image), save=False)
    obj.renditions = {"webp": build_renditions(image, f"cms/renditions/{uuid.uuid4().hex}", widths)}
    _library_processed(obj, asset)


def _library_original(file, actor, request):
    # Compatibility forms keep their synchronous outputs, but preserve the full
    # uncropped source in the same library as new editor uploads.
    if actor is None:
        return None
    from .media import upload

    return upload(file, actor, request, audit=False)[0]


def _library_changed_alt(obj, actor):
    ref = obj.image_reference
    if not ref or not obj.pk or actor is None:
        return
    previous = type(obj).objects.filter(pk=obj.pk).first()
    field = "alt" if isinstance(obj, HeroSlide) else "image_alt"
    names = [f"{field}_{lang}" for lang in ("es", "en")]
    if (
        not previous
        or previous.image_reference != ref
        or all(getattr(previous, name) == getattr(obj, name) for name in names)
    ):
        return
    from copy import deepcopy

    from .models import MediaAsset
    from .registry import text, validate_fields

    alt = {lang: getattr(obj, f"{field}_{lang}") or "" for lang in ("es", "en")}
    validate_fields((text("alt", "Texto alternativo", 300, required=True),), {"alt": alt})
    asset = MediaAsset.objects.select_for_update(of=("self",)).get(pk=ref["asset"])
    payload = deepcopy(asset.versions[str(ref["version"])][ref["crop"]])
    payload["alt"] = alt
    asset.version += 1
    asset.versions = {**asset.versions, str(asset.version): {ref["crop"]: payload}}
    asset.alt_es, asset.alt_en, asset.state = alt["es"], alt["en"], "ready"
    asset.save(update_fields=["version", "versions", "alt_es", "alt_en", "state"])
    obj.image_reference = {**ref, "version": asset.version}


def _library_processed(obj, asset):
    if asset is None:
        return
    from .models import MediaAsset
    from .selectors import image_data

    asset = MediaAsset.objects.select_for_update(of=("self",)).get(pk=asset.pk)
    payloads = [image_data(obj, lang) for lang in ("es", "en")]
    payload = {
        **payloads[0],
        "alt": {lang: payloads[i]["alt"] for i, lang in enumerate(("es", "en"))},
    }
    ratio = (
        "16:9"
        if (getattr(obj, "kind", "") == "hero" or getattr(obj, "device", "") == "desktop")
        else "4:5"
    )
    asset.version += 1
    asset.versions = {**asset.versions, str(asset.version): {ratio: payload}}
    asset.alt_es, asset.alt_en = payload["alt"]["es"], payload["alt"]["en"]
    asset.state = "ready"
    asset.save(update_fields=["version", "versions", "alt_es", "alt_en", "state"])
    obj.image_reference = {"asset": asset.pk, "crop": ratio, "version": asset.version}


def editorial_values(obj):
    values = {}
    for field in obj._meta.concrete_fields:
        if field.name in {
            "id",
            "created_at",
            "updated_at",
            "renditions",
            "width",
            "height",
            "version",
            "status",
            "published_at",
        }:
            continue
        if hasattr(obj, f"{field.name}_es"):
            continue
        value = getattr(obj, field.name)
        if field.name == "props" and isinstance(obj, HomeSection):
            from .registry import editorial_props

            # Registry labels can match legacy column labels (notably Imagen).
            # Keep both sources so an empty props slot cannot hide a stored photo.
            for label, prop_value in editorial_props(obj.kind, obj.props).items():
                key = f"Contenido · {label}" if label in values else label
                values[key] = prop_value
            continue
        if field.name == "image_reference":
            value = (
                f"Foto de biblioteca {value['asset']} · {value['crop']} "
                f"· versión {value['version']}"
                if value
                else "Sin foto de biblioteca"
            )
        elif field.name == "image":
            value = "Foto cargada" if value else "Sin foto"
        elif field.is_relation:
            value = str(value) if value else "Sin seleccionar"
        elif isinstance(value, bool):
            value = "Sí" if value else "No"
        elif field.choices:
            value = str(getattr(obj, f"get_{field.name}_display")())
        values[str(field.verbose_name)] = "" if value is None else str(value)
    return values


def editorial_before(obj):
    previous = type(obj).objects.filter(pk=obj.pk).first() if obj.pk else None
    return editorial_values(previous) if previous else {}


def audit_editorial(
    obj, before, actor=None, request=None, action="cms.draft_saved", image_changed=False
):
    after = editorial_values(obj)
    diff = {
        key: [before.get(key, ""), after.get(key, "")]
        for key in dict.fromkeys((*before, *after))
        if before.get(key, "") != after.get(key, "")
    }
    if image_changed and before.get("Imagen", before.get("Foto")) == "Foto cargada":
        diff["Foto"] = ["Foto anterior", "Foto reemplazada"]
    if diff:
        record(action, actor=actor, obj=obj, request=request, diff=diff)


@draft_mutation(lambda obj, *args: document_key(obj))
@transaction.atomic
def save_hero_slide(obj: HeroSlide, actor=None, request=None, *, audit: bool = True) -> None:
    """Single save path for slides; bulk callers pass audit=False and record one event."""
    before = editorial_before(obj)
    image_changed = bool(getattr(obj, "image", None) and not getattr(obj.image, "_committed", True))
    if obj.pk and not obj.image:
        previous = HeroSlide.objects.get(pk=obj.pk)
        if previous.image and previous.image_reference == obj.image_reference:
            # Clearing an upload also clears its automatically attached reference.
            obj.image_reference = {}
    obj.full_clean()
    process_slide_images(obj, actor, request)
    obj.save()
    if audit:
        audit_editorial(obj, before, actor, request, image_changed=image_changed)


@draft_mutation(lambda obj, *args: document_key(obj))
@transaction.atomic
def delete_hero_slide(obj: HeroSlide, actor=None, request=None) -> None:
    record(
        "cms.slide_deleted",
        actor=actor,
        obj=obj,
        request=request,
        diff={"Foto": [obj.alt_es or "Foto de portada", "Eliminada del borrador"]},
    )
    obj.delete()


@draft_mutation(lambda obj, *args: document_key(obj))
@transaction.atomic
def save_section(obj: HomeSection, actor=None, request=None) -> None:
    before = editorial_before(obj)
    image_changed = bool(getattr(obj, "image", None) and not getattr(obj.image, "_committed", True))
    validate_section(obj)
    process_image(obj, actor, request)
    obj.save()
    audit_editorial(obj, before, actor, request, image_changed=image_changed)


@draft_mutation(lambda obj, *args: document_key(obj))
@transaction.atomic
def save_page(obj: Page, actor=None, request=None) -> None:
    if obj.pk and Page.objects.filter(pk=obj.pk).exclude(kind=obj.kind).exists():
        raise ValidationError("El tipo de una página existente no se puede cambiar.")
    before = editorial_before(obj)
    image_changed = bool(getattr(obj, "image", None) and not getattr(obj.image, "_committed", True))
    from .page_options import prepare_slugs

    prepare_slugs(obj)
    if obj.kind == "personalize":
        old = Page.objects.filter(pk=obj.pk).first() if obj.pk else None
        if old is None or any(
            (getattr(old, f"body_{lang}") or "") != (getattr(obj, f"body_{lang}") or "")
            for lang in ("es", "en")
        ):
            obj.body_enabled = True
    obj.full_clean()
    try:
        with transaction.atomic():
            obj.save()
    except IntegrityError as exc:
        raise ValidationError("Otra página ya usa esta dirección. Elige una distinta.") from exc
    audit_editorial(obj, before, actor, request, image_changed=image_changed)


def validate_personalization(obj: PersonalizationService) -> None:
    for locale in ("es", "en"):
        try:
            for _literal, name, spec, conversion in Formatter().parse(
                getattr(obj, f"whatsapp_message_{locale}") or ""
            ):
                if name is not None and (name not in {"service", "url"} or spec or conversion):
                    raise ValueError
        except ValueError as exc:
            raise ValidationError(_("Solo se permiten {service} y {url}.")) from exc
        if obj.image and not getattr(obj, f"image_alt_{locale}", ""):
            raise ValidationError(_("Escribe el texto alternativo en español e inglés."))
    obj.full_clean()


@transaction.atomic
def save_personalization(obj: PersonalizationService, actor=None) -> None:
    require_capability(actor, "edit")
    validate_personalization(obj)
    process_image(obj, actor)
    obj.save()


def section_source(section: HomeSection) -> dict[str, Any]:
    source = {
        field.attname: getattr(section, field.attname)
        for field in section._meta.concrete_fields
        if field.name not in {"created_at", "updated_at", "image"}
    } | {"image": section.image.name}
    source["slides"] = [
        {
            field.attname: (
                getattr(slide, field.attname).name
                if field.name == "image"
                else getattr(slide, field.attname)
            )
            for field in slide._meta.concrete_fields
            if field.name not in {"created_at", "updated_at", "section"}
        }
        for slide in section.slides.all()
    ]
    return source


@transaction.atomic
def publish_home(
    actor: User | AnonymousUser,
    request: HttpRequest | None = None,
    note: str = "",
    *,
    expected_version=None,
) -> HomePublication:
    from .selectors import draft_sections, render_sections

    actor = require_publish(actor)
    document = lock_document("home")
    check_version(document, expected_version, publishing=True)
    if len(note) > 300:
        raise ValidationError("La nota puede tener hasta 300 caracteres.")
    sections = list(draft_sections().select_for_update(of=("self",)))
    latest = HomePublication.objects.first()
    for section in sections:
        if section.is_visible:
            validate_section(section)
            for slide in section.slides.all():
                slide.full_clean()
    source = [section_source(section) for section in sections]
    snapshot = {locale: render_sections(sections, locale) for locale in ("es", "en")}
    from .review_changes import equivalent
    from .section_adapters import home_snapshot, section_sources

    if (
        latest
        and equivalent(home_snapshot(latest.snapshot), snapshot)
        and equivalent(section_sources(latest.draft_snapshot), source)
        and equivalent(latest.seo, document.seo)
    ):
        document.home_publication = latest
        document.published_version = document.draft_version
        document.save(update_fields=["home_publication", "published_version"])
        return latest
    publication = HomePublication.objects.create(
        snapshot=snapshot,
        draft_snapshot=source,
        seo=document.seo,
        published_by=actor,
        published_by_repr=actor.get_username(),
        note=note,
    )
    document.home_publication = publication
    document.published_version = document.draft_version
    document.save(update_fields=["home_publication", "published_version"])
    record("cms.home_published", actor=actor, obj=publication, request=request)
    return publication


@transaction.atomic
def restore_home(
    publication: HomePublication,
    actor: User | AnonymousUser,
    request: HttpRequest | None = None,
    *,
    expected_version=None,
) -> None:
    actor = require_capability(actor, "restore")
    document = lock_document("home")
    check_version(document, expected_version)
    from .registry import get_type, validate_props
    from .section_adapters import section_sources

    sources = section_sources(publication.draft_snapshot)
    for source in sources:
        spec = get_type(source["kind"], source["schema_version"])
        if spec.storage != "columns":
            validate_props(source["kind"], source["props"], source["schema_version"])
    HomeSection.objects.all().delete()

    for source in sources:
        fields = dict(source)
        slides = fields.pop("slides", [])
        # Restore the exact editable source, including incomplete hidden drafts.
        section = HomeSection.objects.create(**fields)
        for slide_source in slides:
            # Old immutable publications retain paired slide sources.
            fields = dict(slide_source)
            mobile = fields.pop("image_mobile", "")
            mobile_data = {
                name: fields.pop(f"mobile_{name}", default)
                for name, default in (("renditions", {}), ("width", 0), ("height", 0))
            }
            if fields.get("image") or not mobile:
                HeroSlide.objects.create(section=section, **fields)
            if mobile:
                fields.pop("id", None)
                HeroSlide.objects.create(
                    section=section,
                    **(fields | mobile_data | {"image": mobile, "device": "mobile"}),
                )
    document.seo = deepcopy(publication.seo)
    document.save(update_fields=["seo"])
    _record_restore(document, publication, actor, home=True)
    record("cms.home_restored", actor=actor, obj=publication, request=request)


PAGE_FIELDS = ("title", "slug", "body", "process_title", "faq_title")


def page_snapshot(page):
    from .selectors import localized

    steps = list(page.process_steps.all())
    questions = list(page.faq_items.all())
    from .page_options import document_seo, draft_path

    snapshot = {"_seo": document_seo(document_key(page)), "_body_enabled": page.body_enabled}
    for locale in ("es", "en"):

        def item(row, fields, locale=locale):
            return {field: localized(row, field, locale) for field in fields} | {
                "source": {field: getattr(row, f"{field}_{locale}") for field in fields},
                "position": row.position,
            }

        data = {field: localized(page, field, locale) for field in PAGE_FIELDS}
        if locale in page.slug_paths:
            data["slug"] = page.slug_paths[locale].rstrip("/").rsplit("/", 1)[-1]
        snapshot[locale] = data | {
            "path": draft_path(page, locale),
            "body_html": render_markdown(data["body"]),
            "source": {field: getattr(page, f"{field}_{locale}") for field in PAGE_FIELDS},
            "process": {
                "title": data["process_title"],
                "steps": [item(row, ("title", "description")) for row in steps],
            },
            "faq": {
                "title": data["faq_title"],
                "items": [
                    item(row, ("question", "answer"))
                    | {"answer_html": render_markdown(localized(row, "answer", locale))}
                    for row in questions
                ],
            },
        }
    return snapshot


@transaction.atomic
def publish_page(
    page: Page,
    actor: User | AnonymousUser,
    request: HttpRequest | None = None,
    note: str = "",
    *,
    expected_version=None,
) -> PageRevision:
    actor = require_publish(actor)
    lock_document("home")
    document = lock_document(document_key(page))
    check_version(document, expected_version, publishing=True)
    if len(note) > 300:
        raise ValidationError("La nota puede tener hasta 300 caracteres.")
    locked = Page.objects.select_for_update(of=("self",)).get(pk=page.pk)
    latest = locked.revisions.first()
    snapshot = page_snapshot(locked)
    from .review_changes import equivalent, page_groups

    if (
        latest
        and not page_groups(snapshot, latest.snapshot, kind=locked.kind)
        and equivalent(snapshot.get("_seo", {}), latest.snapshot.get("_seo", {}))
    ):
        document.page_revision = latest
        document.published_version = document.draft_version
        document.save(update_fields=["page_revision", "published_version"])
        return latest
    from .page_options import validate_addresses
    from .redirects import on_page_publish

    validate_addresses(locked)
    locked.full_clean()
    for row in [*locked.process_steps.all(), *locked.faq_items.all()]:
        row.full_clean()
    revision = PageRevision.objects.create(
        page=locked,
        version=locked.version + 1,
        snapshot=snapshot,
        note=note,
        published_by=actor,
        published_by_repr=actor.get_username(),
    )
    on_page_publish(locked, latest, snapshot, actor)
    locked.version = revision.version
    locked.status = "published"
    locked.published_at = timezone.now()
    locked.save()
    page.refresh_from_db()
    document.page_revision = revision
    document.published_version = document.draft_version
    document.save(update_fields=["page_revision", "published_version"])
    record("cms.page_published", actor=actor, obj=page, request=request)
    return revision


@transaction.atomic
def restore_page_revision(
    revision: PageRevision,
    actor: User | AnonymousUser,
    request: HttpRequest | None = None,
    *,
    expected_version=None,
) -> None:
    actor = require_capability(actor, "restore")
    document = lock_document(document_key(revision.page))
    check_version(document, expected_version)
    page = Page.objects.select_for_update(of=("self",)).get(pk=revision.page_id)
    for locale in ("es", "en"):
        source = revision.snapshot[locale].get("source", revision.snapshot[locale])
        for field in PAGE_FIELDS:
            if field in source:
                setattr(page, f"{field}_{locale}", source[field])
    page.slug_paths = {
        lang: revision.snapshot[lang]["path"]
        for lang in ("es", "en")
        if "path" in revision.snapshot[lang]
    }
    page.body_enabled = revision.snapshot.get("_body_enabled", False)
    document.seo = deepcopy(revision.snapshot.get("_seo", {}))
    document.save(update_fields=["seo"])
    # Old snapshots have no child source: retain the draft children safely.
    for key, model, relation, fields in (
        ("process", ProcessStep, "process_steps", ("title", "description")),
        ("faq", FaqItem, "faq_items", ("question", "answer")),
    ):
        list_key = "steps" if key == "process" else "items"
        if key not in revision.snapshot["es"]:
            continue
        getattr(page, relation).all().delete()
        for index, data in enumerate(revision.snapshot["es"][key][list_key]):
            values = {"page": page, "position": data.get("position", index)}
            for locale in ("es", "en"):
                row = revision.snapshot[locale][key][list_key][index]
                for field in fields:
                    values[f"{field}_{locale}"] = row.get("source", row).get(field, "")
            model.objects.create(**values)
    page.save()
    _record_restore(document, revision, actor)
    record("cms.page_restored", actor=actor, obj=page, request=request)


@draft_mutation(lambda obj, *args: document_key(obj))
@draft_mutation(lambda obj, *args: document_key(obj))
@transaction.atomic
def save_page_item(obj, actor=None, request=None):
    if obj.pk and type(obj).objects.filter(pk=obj.pk).exclude(page_id=obj.page_id).exists():
        raise ValidationError("Este contenido pertenece a otra página.")
    Page.objects.select_for_update(of=("self",)).get(pk=obj.page_id)
    before = editorial_before(obj)
    obj.full_clean()
    from .registry import FAQ_FIELDS, STEP_FIELDS, validate_fields

    fields = STEP_FIELDS if isinstance(obj, ProcessStep) else FAQ_FIELDS
    from .registry import REGISTRY

    kind, relation = (
        ("process", "process_steps") if isinstance(obj, ProcessStep) else ("faq", "faq_items")
    )
    limit = next(field.max for field in REGISTRY[kind].fields if field.type == "list")
    if obj._state.adding and getattr(obj.page, relation).count() >= limit:
        raise ValidationError({"__all__": f"Usa como máximo {limit} elementos."})
    # Existing models intentionally retain the Phase 1 Spanish fallback.
    validate_fields(
        fields,
        {
            field.key: {
                lang: getattr(obj, f"{field.key}_{lang}", "")
                or getattr(obj, f"{field.key}_es", "")
                or ""
                for lang in ("es", "en")
            }
            for field in fields
        },
    )
    obj.save()
    audit_editorial(obj, before, actor, request)


@draft_mutation(lambda obj, *args: document_key(obj))
@transaction.atomic
def delete_page_item(obj, actor=None, request=None):
    Page.objects.select_for_update(of=("self",)).get(pk=obj.page_id)
    record(
        "cms.page_item_deleted",
        actor=actor,
        obj=obj,
        request=request,
        diff={"Contenido": [str(obj), "Eliminado del borrador"]},
    )
    obj.delete()


def _record_restore(document, origin, actor, home=False):
    document.draft_version += 1
    document.updated_by = actor
    document.save(update_fields=["draft_version", "updated_by", "updated_at"])
    snapshot = (
        [section_source(row) for row in HomeSection.objects.prefetch_related("slides").all()]
        if home
        else page_snapshot(Page.objects.get(pk=origin.page_id))
    )
    DraftRevision.objects.create(
        document=document,
        draft_version=document.draft_version,
        snapshot=snapshot,
        seo=deepcopy(document.seo),
        published_by=actor,
        published_by_repr=actor.get_username(),
        **{"restored_from_home" if home else "restored_from_page": origin},
    )
