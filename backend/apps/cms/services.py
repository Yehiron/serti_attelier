from __future__ import annotations

import html
import uuid
from string import Formatter
from typing import Any

import markdown  # type: ignore[import-untyped]
import nh3
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
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

from .models import (
    HeroSlide,
    HomePublication,
    HomeSection,
    Page,
    PageRevision,
    PersonalizationService,
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
    if obj.image:
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


def process_image(obj: HomeSection | PersonalizationService) -> None:
    if not obj.image:
        obj.renditions, obj.width, obj.height = {}, 0, 0
        return
    if getattr(obj.image, "_committed", True):
        return
    image = validated_image(obj.image)
    if ratio := display_ratio(obj):
        image = crop_to_ratio(image, *ratio)
    image = cap_master(image)
    obj.width, obj.height = image.size
    obj.image.save(f"{uuid.uuid4().hex}.webp", encode_webp(image), save=False)
    paths = build_renditions(image, f"cms/renditions/{uuid.uuid4().hex}", (960, 1600, 2400))
    obj.renditions = {"webp": paths}


def process_slide_images(obj: HeroSlide) -> None:
    # Validate both uploads before writing either image to storage.
    decoded = {
        field: cap_master(validated_image(upload))
        for field in ("image", "image_mobile")
        if (upload := getattr(obj, field)) and not getattr(upload, "_committed", True)
    }
    for field, prefix, widths in (
        ("image", "", (960, 1600, 2400)),
        ("image_mobile", "mobile_", (480, 960, 1600)),
    ):
        upload = getattr(obj, field)
        if not upload:
            setattr(obj, f"{prefix}renditions", {})
            setattr(obj, f"{prefix}width", 0)
            setattr(obj, f"{prefix}height", 0)
        elif field in decoded:
            image = decoded[field]
            upload.save(f"{uuid.uuid4().hex}.webp", encode_webp(image), save=False)
            paths = build_renditions(image, f"cms/renditions/{uuid.uuid4().hex}", widths)
            setattr(obj, f"{prefix}renditions", {"webp": paths})
            setattr(obj, f"{prefix}width", image.width)
            setattr(obj, f"{prefix}height", image.height)


@transaction.atomic
def save_hero_slide(obj: HeroSlide) -> None:
    obj.full_clean()
    process_slide_images(obj)
    obj.save()


@transaction.atomic
def delete_hero_slide(obj: HeroSlide) -> None:
    obj.delete()


@transaction.atomic
def save_section(obj: HomeSection) -> None:
    validate_section(obj)
    process_image(obj)
    obj.save()


@transaction.atomic
def save_page(obj: Page) -> None:
    obj.full_clean()
    obj.save()


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
def save_personalization(obj: PersonalizationService) -> None:
    validate_personalization(obj)
    process_image(obj)
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
                if field.name in {"image", "image_mobile"}
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
    actor: User | AnonymousUser, request: HttpRequest | None = None, note: str = ""
) -> HomePublication:
    from .selectors import draft_sections, render_sections

    actor = require_publish(actor)
    sections = list(draft_sections().select_for_update(of=("self",)))
    for section in sections:
        if section.is_visible:
            validate_section(section)
            for slide in section.slides.all():
                slide.full_clean()
    publication = HomePublication.objects.create(
        snapshot={locale: render_sections(sections, locale) for locale in ("es", "en")},
        draft_snapshot=[section_source(section) for section in sections],
        published_by=actor,
        published_by_repr=actor.get_username(),
        note=note,
    )
    record("cms.home_published", actor=actor, obj=publication, request=request)
    return publication


@transaction.atomic
def restore_home(
    publication: HomePublication, actor: User | AnonymousUser, request: HttpRequest | None = None
) -> None:
    actor = require_publish(actor)
    HomeSection.objects.all().delete()
    for source in publication.draft_snapshot:
        fields = dict(source)
        slides = fields.pop("slides", [])
        # Restore the exact editable source, including incomplete hidden drafts.
        section = HomeSection.objects.create(**fields)
        for slide_source in slides:
            HeroSlide.objects.create(section=section, **slide_source)
    record("cms.home_restored", actor=actor, obj=publication, request=request)


@transaction.atomic
def publish_page(
    page: Page, actor: User | AnonymousUser, request: HttpRequest | None = None
) -> PageRevision:
    actor = require_publish(actor)
    locked = Page.objects.select_for_update().get(pk=page.pk)
    locked.full_clean()
    snapshot = {}
    for locale in ("es", "en"):
        data = {
            field: getattr(locked, f"{field}_{locale}") or getattr(locked, f"{field}_es") or ""
            for field in ("title", "slug", "body")
        }
        snapshot[locale] = data | {
            "body_html": render_markdown(data["body"]),
            "source": {
                field: getattr(locked, f"{field}_{locale}") for field in ("title", "slug", "body")
            },
        }
    revision = PageRevision.objects.create(
        page=locked,
        version=locked.version + 1,
        snapshot=snapshot,
        published_by=actor,
        published_by_repr=actor.get_username(),
    )
    locked.version = revision.version
    locked.status = "published"
    locked.published_at = timezone.now()
    locked.save()
    page.refresh_from_db()
    record("cms.page_published", actor=actor, obj=page, request=request)
    return revision


@transaction.atomic
def restore_page_revision(
    revision: PageRevision, actor: User | AnonymousUser, request: HttpRequest | None = None
) -> None:
    actor = require_publish(actor)
    page = Page.objects.select_for_update().get(pk=revision.page_id)
    for locale in ("es", "en"):
        for field in ("title", "slug", "body"):
            setattr(
                page,
                f"{field}_{locale}",
                revision.snapshot[locale].get("source", revision.snapshot[locale])[field],
            )
    page.save()
    record("cms.page_restored", actor=actor, obj=page, request=request)
