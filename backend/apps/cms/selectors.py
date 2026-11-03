from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import F, QuerySet, Window
from django.db.models.functions import RowNumber
from django.utils.translation import override

from apps.catalog.api.serializers import PieceListSerializer
from apps.catalog.models import CollectionPiece, Piece, Stone
from apps.catalog.selectors import cover_data, published_pieces
from apps.core.routes import href
from apps.core.selectors import get_solo

from .models import (
    HeroSlide,
    HomePublication,
    HomeSection,
    Page,
    PageRevision,
    PersonalizationService,
)
from .services import render_markdown

LEGAL_KINDS = ("terms", "privacy", "returns", "shipping", "cookies")


def localized(obj: Any, field: str, locale: str) -> str:
    return str(getattr(obj, f"{field}_{locale}", "") or getattr(obj, f"{field}_es", "") or "")


def draft_sections() -> QuerySet[HomeSection]:
    return HomeSection.objects.select_related(
        "collection", "cta_category", "cta_stone", "cta_collection", "cta_piece", "cta_page"
    ).prefetch_related("slides")


def image_data(
    obj: HomeSection | PersonalizationService | HeroSlide, locale: str, mobile: bool = False
) -> dict[str, Any] | None:
    image = obj.image
    prefix = ""
    if not image:
        return None
    paths = getattr(obj, f"{prefix}renditions").get("webp", {})
    src = (
        default_storage.url(paths.get("960") or paths[max(paths, key=int)]) if paths else image.url
    )
    return {
        "src": src,
        "srcset": ", ".join(
            f"{default_storage.url(path)} {width}w"
            for width, path in sorted(paths.items(), key=lambda item: int(item[0]))
        ),
        "width": getattr(obj, f"{prefix}width"),
        "height": getattr(obj, f"{prefix}height"),
        "alt": localized(obj, "alt" if isinstance(obj, HeroSlide) else "image_alt", locale),
    }


def render_sections(sections: list[HomeSection], locale: str) -> list[dict[str, Any]]:
    result = []
    for obj in sections:
        if not obj.is_visible:
            continue
        data: dict[str, Any] = {
            "id": obj.pk,
            "kind": obj.kind,
            "title": localized(obj, "title", locale),
        }
        if obj.kind in {"hero", "stone_panels", "collection_rail"}:
            data["subtitle"] = localized(obj, "subtitle", locale)
        if obj.kind in {"statement", "story", "personalize", "banner"}:
            data["body"] = localized(obj, "body", locale)
        if obj.kind in {"hero", "story", "personalize", "banner"}:
            data["image"] = image_data(obj, locale)
            data["cta"] = None
            if obj.cta_kind != "none":
                target = getattr(obj, f"cta_{obj.cta_kind}", None)
                data["cta"] = {
                    "label": localized(obj, "cta_label", locale),
                    "href": obj.cta_external_url
                    if obj.cta_kind == "external"
                    else href(obj.cta_kind, locale, target),
                    "external": obj.cta_kind == "external",
                }
        if obj.kind == "hero":
            slides = []
            for slide in sorted(
                obj.slides.all(), key=lambda row: (row.device != "desktop", row.position, row.pk)
            ):
                if slide.width and slide.height and slide.image:
                    image = image_data(slide, locale)
                    slides.append(
                        {
                            "image": image if slide.device == "desktop" else None,
                            "mobile_image": image if slide.device == "mobile" else None,
                        }
                    )
            data["slides"] = slides
            data["image"] = next(
                (slide["image"] for slide in slides if slide["image"]), data["image"]
            )
        if obj.kind == "collection_rail":
            data["collection_id"] = obj.collection_id
            data["collection"] = {
                "slug": localized(obj.collection, "slug", locale),
                "name": localized(obj.collection, "name", locale),
                "href": href("collection", locale, obj.collection),
            }
        if obj.kind == "stone_panels":
            data["stones_live"] = True
        result.append(data)
    return result


def resolve_live(sections: list[dict[str, Any]], locale: str) -> list[dict[str, Any]]:
    sections = deepcopy(sections)
    collection_ids = {
        section["collection_id"] for section in sections if section["kind"] == "collection_rail"
    }
    rails: dict[int, list[Piece]] = {pk: [] for pk in collection_ids}
    if collection_ids:
        # Fetch associations and all matching cards once, independent of section count.
        links = list(
            CollectionPiece.objects.filter(
                collection_id__in=collection_ids, piece__status="published"
            )
            .exclude(piece__sale_state="sold")
            .annotate(
                rail_position=Window(
                    RowNumber(),
                    partition_by=[F("collection_id")],
                    order_by=[F("position").asc(), F("pk").asc()],
                )
            )
            .filter(rail_position__lte=8)
            .values_list("collection_id", "piece_id")
        )
        pieces = {
            piece.pk: piece
            for piece in published_pieces()
            .filter(pk__in={pk for _, pk in links})
            .exclude(sale_state="sold")
        }
        for collection_id, piece_id in links:
            if piece_id in pieces and len(rails[collection_id]) < 8:
                rails[collection_id].append(pieces[piece_id])
    stones = []
    if any(section["kind"] == "stone_panels" for section in sections):
        for stone in Stone.objects.all():
            image = cover_data(stone, locale)
            stones.append(
                {
                    "slug": localized(stone, "slug", locale),
                    "name": localized(stone, "name", locale),
                    "description": localized(stone, "description", locale),
                    "image": image,
                    "href": href("stone", locale, stone),
                }
            )
    with override(locale):
        for section in sections:
            if section["kind"] == "collection_rail":
                section["pieces"] = list(
                    PieceListSerializer(rails[section.pop("collection_id")], many=True).data
                )
            if section["kind"] == "stone_panels":
                section.pop("stones_live", None)
                section["stones"] = stones
    return sections


def home(locale: str, preview: bool = False) -> dict[str, Any]:
    publication = HomePublication.objects.first()
    sections = (
        render_sections(list(draft_sections()), locale)
        if preview
        else (publication.snapshot[locale] if publication else [])
    )
    return {
        "sections": resolve_live(sections, locale),
        "published_at": publication.published_at.isoformat() if publication else None,
        "preview": preview,
    }


def page_path(kind: str, locale: str, slug_es: str, slug_en: str) -> str:
    return href(
        {"manufacturer": "story", "personalize": "personalize", "contact": "contact"}.get(
            kind, "page"
        ),
        locale,
        SimpleNamespace(slug_es=slug_es, slug_en=slug_en),
    )


def page_payload(page: Page, locale: str, revision: PageRevision | None = None) -> dict[str, Any]:
    if revision:
        content = revision.snapshot
    else:
        content = {
            lang: {field: localized(page, field, lang) for field in ("title", "slug", "body")}
            for lang in ("es", "en")
        }
        for data in content.values():
            data["body_html"] = render_markdown(data["body"])
    return {
        "kind": page.kind,
        "slug": content[locale]["slug"],
        "title": content[locale]["title"],
        "body_html": content[locale]["body_html"],
        "version": revision.version if revision else page.version,
        "updated_at": (revision.published_at if revision else page.updated_at).isoformat(),
        "alternates": {
            lang: page_path(page.kind, lang, content["es"]["slug"], content["en"]["slug"])
            for lang in ("es", "en")
        },
    }


def published_pages() -> list[tuple[Page, PageRevision]]:
    pages = Page.objects.filter(status="published").prefetch_related("revisions")
    return [(page, next(iter(page.revisions.all()))) for page in pages if page.version]


def personalization(locale: str) -> dict[str, Any]:
    config = get_solo()
    services = []
    for obj in PersonalizationService.objects.filter(is_active=True):
        message = localized(obj, "whatsapp_message", locale).format(
            service=localized(obj, "title", locale),
            url=settings.PUBLIC_SITE_URL + href("personalize", locale),
        )
        services.append(
            {
                "id": obj.pk,
                "title": localized(obj, "title", locale),
                "description": localized(obj, "description", locale),
                "image": image_data(obj, locale),
                "whatsapp_url": (
                    f"https://wa.me/{config.whatsapp_number}?" + urlencode({"text": message})
                )
                if config.whatsapp_number
                else None,
            }
        )
    return {"services": services}


def site_settings(locale: str) -> dict[str, Any]:
    config = get_solo()
    legal = {
        page.kind: page_payload(page, locale, revision)
        for page, revision in published_pages()
        if page.kind in LEGAL_KINDS
    }
    message = localized(config, "whatsapp_general", locale).format(
        name="SERTI", sku="", url=settings.PUBLIC_SITE_URL + href("home", locale)
    )
    return {
        "whatsapp": {
            "number": config.whatsapp_number or None,
            "general_url": (
                f"https://wa.me/{config.whatsapp_number}?" + urlencode({"text": message})
            )
            if config.whatsapp_number
            else None,
        },
        "social": [
            {"network": network, "url": getattr(config, f"{network}_url")}
            for network in ("instagram", "facebook", "tiktok", "pinterest")
            if getattr(config, f"{network}_url")
        ],
        "support_email": config.support_email or None,
        "certificate_price_cents": config.certificate_price_cents,
        "legal_versions": {
            kind: legal[kind]["version"] if kind in legal else None for kind in ("terms", "privacy")
        },
        "legal_pages": [
            {"kind": kind, "title": legal[kind]["title"], "href": legal[kind]["alternates"][locale]}
            for kind in LEGAL_KINDS
            if kind in legal
        ],
    }
