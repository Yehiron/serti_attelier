"""Page addresses and SEO share the existing versioned document boundary."""

import re
from copy import deepcopy
from urllib.parse import unquote, urlsplit

from django.core.exceptions import ValidationError
from django.utils.text import slugify

from apps.core.routes import ROUTES

from .models import ContentDocument, Page

LEGAL_KINDS = {"terms", "privacy", "returns", "shipping", "cookies"}
RESERVED = {segment for pair in ROUTES.values() for segment in pair if segment} | {
    "api",
    "dashboard",
    "_next",
    "media",
    "static",
    "preview",
    "admin",
    "healthz",
    "robots",
    "sitemap",
    "es",
    "en",
    "favicon",
    "login",
    "logout",
}


def normalize_slug(value):
    if not isinstance(value, str):
        raise ValidationError("Escribe una dirección de página.")
    value = re.sub(r"[-_]+", "-", slugify(value.strip(), allow_unicode=False)).strip("-")
    if not value or len(value) > 250:
        raise ValidationError("Escribe una dirección de hasta 250 caracteres.")
    return value


def legacy_path(kind, locale, slug):
    route = {"manufacturer": "story", "personalize": "personalize", "contact": "contact"}.get(kind)
    segment = ROUTES[route][locale == "en"] if route else f"legal/{slug}"
    return f"/{locale}/{segment}"


def draft_path(page, locale):
    return page.slug_paths.get(locale) or legacy_path(
        page.kind, locale, getattr(page, f"slug_{locale}") or page.slug_es
    )


def snapshot_path(page, snapshot, locale):
    return snapshot[locale].get("path") or legacy_path(page.kind, locale, snapshot[locale]["slug"])


def prepare_slugs(page):
    old = Page.objects.filter(pk=page.pk).first() if page.pk else None
    paths = deepcopy(page.slug_paths)
    for lang in ("es", "en"):
        field = f"slug_{lang}"
        value = getattr(page, field) or (page.slug_es if lang == "en" else "")
        # Historical blank English slugs keep their fallback until explicitly edited.
        if old and getattr(old, field) == getattr(page, field):
            continue
        own_route = {
            "manufacturer": "story",
            "personalize": "personalize",
            "contact": "contact",
        }.get(page.kind)
        if own_route and not getattr(page, field):
            # A historical blank translation still resolves to its own fixed route.
            continue
        value = normalize_slug(value)
        if old and value == (getattr(old, field) or (old.slug_es if lang == "en" else "")):
            setattr(page, field, value)
            continue
        own_fixed = own_route and value == ROUTES[own_route][lang == "en"]
        if value in RESERVED and not own_fixed:
            raise ValidationError(
                {field: "Esta dirección está reservada para otra parte de la tienda."}
            )
        path = f"/{lang}/{value}"
        for other in Page.objects.exclude(pk=page.pk).prefetch_related("revisions"):
            if value == (getattr(other, field) or other.slug_es) or path == draft_path(other, lang):
                raise ValidationError({field: "Otra página ya usa esta dirección."})
            for publication in list(other.revisions.all())[:1]:
                if path == snapshot_path(other, publication.snapshot, lang):
                    raise ValidationError({field: "Otra página publicada ya usa esta dirección."})
        from .models import Redirect

        if Redirect.objects.filter(from_path=path, is_active=True, origin="manual").exists():
            raise ValidationError(
                {field: "Esta dirección tiene una redirección manual activa. Desactívala primero."}
            )
        setattr(page, field, value)
        if old:
            paths[lang] = path
    page.slug_paths = paths


def internal_path(value):
    if not isinstance(value, str) or len(value) > 500:
        raise ValidationError("Usa una dirección interna que empiece por /es/ o /en/.")
    decoded = value
    for _ in range(3):
        decoded = unquote(decoded)
    if (
        not re.fullmatch(r"/(es|en)(/[a-zA-Z0-9/_-]*)?", decoded)
        or decoded != value
        or "//" in value
        or any(part in {".", ".."} for part in value.split("/"))
        or urlsplit(value).query
        or urlsplit(value).fragment
    ):
        raise ValidationError(
            "Usa una dirección interna que empiece por /es/ o /en/, sin parámetros."
        )
    if len(value.split("/")) > 2 and value.split("/")[2] in {
        "api",
        "dashboard",
        "_next",
        "media",
        "static",
        "preview",
    }:
        raise ValidationError("Esta dirección está reservada.")
    return value.rstrip("/")


def validate_seo(value, previous, actor):
    from .documents import require_capability
    from .media import validate_reference

    if not isinstance(value, dict) or set(value) - {"title", "description", "image", "noindex"}:
        raise ValidationError("Revisa las opciones para buscadores.")
    cleaned = {}
    for field, limit in (("title", 60), ("description", 155)):
        texts = value.get(field, {})
        if not isinstance(texts, dict) or set(texts) - {"es", "en"}:
            raise ValidationError("Escribe los textos en español e inglés.")
        for lang, text in texts.items():
            if not isinstance(text, str) or len(text) > limit:
                raise ValidationError({f"{field}.{lang}": f"Usa hasta {limit} caracteres."})
        if any(texts.values()):
            cleaned[field] = texts
    noindex = value.get("noindex", False)
    if type(noindex) is not bool:
        raise ValidationError("Selecciona si quieres ocultar la página en buscadores.")
    if noindex != previous.get("noindex", False):
        require_capability(actor, "publish")
    if noindex:
        cleaned["noindex"] = True
    if value.get("image"):
        ref = validate_reference(value["image"], selecting=True)
        if ref["crop"] != "1.91:1":
            raise ValidationError("Elige el recorte 1.91:1 para compartir la página.")
        cleaned["image"] = ref
    return cleaned


def public_seo(value, locale):
    from .media import resolve

    return {
        "title": value.get("title", {}).get(locale, ""),
        "description": value.get("description", {}).get(locale, ""),
        "image": resolve(value["image"], locale) if value.get("image") else None,
        "noindex": value.get("noindex", False),
    }


def seo_groups(current, previous):
    from .review_changes import display, equivalent

    rows = []
    for field, label in (("title", "Título SEO"), ("description", "Descripción SEO")):
        for lang in ("es", "en"):
            left, right = previous.get(field, {}).get(lang), current.get(field, {}).get(lang)
            if not equivalent(left, right):
                rows.append(
                    {
                        "label": f"{label} · {lang.upper()}",
                        "before": display(left),
                        "after": display(right),
                    }
                )
    for field, label in (("image", "Foto para compartir"), ("noindex", "No indexar")):
        left, right = previous.get(field), current.get(field)
        if field == "noindex":
            left, right = bool(left), bool(right)
        if not equivalent(left, right):
            rows.append({"label": label, "before": display(left), "after": display(right)})
    return [{"name": "Buscadores y redes sociales", "icon": "search", "rows": rows}] if rows else []


def document_seo(key):
    return ContentDocument.objects.filter(key=key).values_list("seo", flat=True).first() or {}


def validate_addresses(page):
    from .models import Redirect

    others = list(Page.objects.exclude(pk=page.pk).prefetch_related("revisions"))
    for lang in ("es", "en"):
        path = draft_path(page, lang)
        if lang in page.slug_paths:
            slug = path.rstrip("/").rsplit("/", 1)[-1]
            # Restored legacy publications may retain their original prefixed path.
            if (
                slug in RESERVED or path != f"/{lang}/{normalize_slug(slug)}"
            ) and path != legacy_path(page.kind, lang, slug):
                raise ValidationError("Esta dirección está reservada para otra parte de la tienda.")
        for other in others:
            revision = next(iter(other.revisions.all()), None)
            if path == draft_path(other, lang) or (
                revision and path == snapshot_path(other, revision.snapshot, lang)
            ):
                raise ValidationError("Otra página ya usa esta dirección.")
        if Redirect.objects.filter(from_path=path, is_active=True, origin="manual").exists():
            raise ValidationError(
                "Esta dirección tiene una redirección manual activa. Desactívala primero."
            )
