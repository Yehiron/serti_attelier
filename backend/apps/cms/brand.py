"""Limited identity document; no CSS or font URLs can enter editorial content."""

import re
from copy import deepcopy

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import transaction
from PIL import Image

from apps.audit.services import record

from .documents import check_version, lock_document, require_capability
from .models import BrandPublication, ContentDocument, DraftRevision, MediaAsset

KEY = "brand:identity"
COLORS = {
    "wine": "#651c32",
    "crimson": "#8a1538",
    "cream": "#ead9cb",
    "paper": "#dfc9b8",
    "ink": "#330414",
    "olive": "#7a7256",
    "olive-deep": "#58513d",
}
COLOR_LABELS = {
    "wine": "Color principal",
    "crimson": "Acento",
    "cream": "Fondo",
    "paper": "Superficie",
    "ink": "Texto",
    "olive": "Oliva",
    "olive-deep": "Oliva oscuro",
}
SLOTS = {
    "logo_light": "Logotipo para fondo claro",
    "logo_dark": "Logotipo para fondo oscuro",
    "monogram_light": "Monograma para fondo claro",
    "monogram_dark": "Monograma para fondo oscuro",
    "footer": "Monograma con lema (pie)",
    "icon": "Ícono del sitio",
    "sharing": "Imagen por defecto al compartir",
}
DEFAULT = {
    **COLORS,
    "title_font": "ninna",
    "text_font": "inter",
    "title_scale": 100,
    "text_scale": 100,
    **dict.fromkeys(SLOTS),
}
LABELS = {
    **COLOR_LABELS,
    **SLOTS,
    "title_font": "Fuente de títulos",
    "text_font": "Fuente del texto",
    "title_scale": "Tamaño de los títulos",
    "text_scale": "Tamaño del texto",
}


def luminance(color):
    channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    return sum(
        weight * (v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
        for weight, v in zip((0.2126, 0.7152, 0.0722), channels, strict=True)
    )


def contrast(a, b):
    light, dark = sorted((luminance(a), luminance(b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def contrast_message(label, ratio, minimum):
    ok = ratio >= minimum
    if not ok:
        label = (
            label.replace(" se lee bien", " no se lee bien")
            .replace(" se leen bien", " no se leen bien")
            .replace(" se distingue", " no se distingue")
        )
    number = f"{ratio:.2f}".replace(".", ",")
    threshold = str(minimum).replace(".", ",")
    advice = "" if ok else " Oscurece el color oscuro o aclara el fondo."
    if not ok and label.startswith("El texto sobre"):
        advice = " Oscurece el texto o aclara el fondo."
    return f"{'✓' if ok else '✗'} {label} ({number}:1; mínimo {threshold}:1).{advice}"


def checks(value):
    return [
        {
            "label": label
            if ratio >= minimum
            else label.replace(" se lee bien", " no se lee bien")
            .replace(" se leen bien", " no se leen bien")
            .replace(" se distingue", " no se distingue"),
            "message": contrast_message(label, ratio, minimum),
            "ratio": round(ratio, 2),
            "ok": ratio >= minimum,
            "required": minimum == 4.5,
        }
        for label, a, b, minimum in (
            ("El texto sobre el fondo se lee bien", "ink", "cream", 4.5),
            ("El texto del botón se lee bien", "cream", "wine", 4.5),
            ("Los enlaces y el encabezado se leen bien", "wine", "cream", 4.5),
            ("El texto al pasar sobre el botón se lee bien", "cream", "crimson", 4.5),
            ("El texto pequeño oliva oscuro se lee bien", "olive-deep", "cream", 4.5),
            ("El corazón de favoritos se distingue del fondo", "emerald", "cream", 3),
        )
        for ratio in [contrast("#0b6e4f" if a == "emerald" else value[a], value[b])]
    ]


def validate(value, *, publishing=False, selecting=False):
    if not isinstance(value, dict) or set(value) != set(DEFAULT):
        raise ValidationError("Revisa los campos de la identidad de marca.")
    result = deepcopy(value)
    for key in COLORS:
        if not isinstance(value[key], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value[key]):
            raise ValidationError(f"{LABELS[key]}: escribe un color como #651c32.")
        result[key] = value[key].lower()
    # Preserve the official gold-on-dark / wine-on-light logo contexts.
    if luminance(result["wine"]) > 0.08 or luminance(result["cream"]) < 0.60:
        raise ValidationError(
            "Mantén el principal oscuro y el fondo claro para proteger los logos oficiales."
        )
    if result["title_font"] not in ("ninna", "cormorant") or result["text_font"] != "inter":
        raise ValidationError("Elige una de las fuentes disponibles.")
    for key in ("title_scale", "text_scale"):
        if type(result[key]) is not int or result[key] not in (90, 100, 110, 120):
            raise ValidationError("Elige un tamaño de 90, 100, 110 o 120 %.")
    for slot in SLOTS:
        if result[slot] is not None:
            result[slot] = validate_logo(slot, result[slot], selecting=selecting)
    if publishing and any(row["required"] and not row["ok"] for row in checks(result)):
        raise ValidationError(
            "No se puede publicar: hay texto con contraste menor a 4,5:1. "
            "Ajusta los colores señalados."
        )
    return result


def validate_logo(slot, ref, *, selecting=False):
    from .media import validate_reference

    ref = validate_reference(ref, selecting=selecting)
    if slot == "sharing":
        if ref["crop"] != "1.91:1":
            raise ValidationError("La imagen para compartir necesita proporción 1.91:1.")
        return ref
    asset = MediaAsset.objects.get(pk=ref["asset"])
    with asset.original.open("rb") as source, Image.open(source) as image:
        image.load()
        if image.format not in {"PNG", "WEBP"}:
            raise ValidationError("Usa PNG o WebP. SVG se rechaza porque puede contener scripts.")
        if slot == "icon":
            if image.width != image.height or image.width < 512:
                raise ValidationError("El ícono debe ser cuadrado y medir al menos 512 x 512 px.")
            if not asset.versions[str(ref["version"])].get("brand_icons"):
                raise ValidationError(
                    "Prepara de nuevo la foto en la biblioteca para generar sus íconos."
                )
        elif image.mode != "RGBA" or image.getchannel("A").getextrema()[0] == 255:
            raise ValidationError("El logo debe ser PNG o WebP con fondo transparente.")
        elif image.width < 96 or image.height < (24 if slot.startswith("monogram") else 32):
            raise ValidationError(
                "El logo es demasiado pequeño. Usa al menos 96 px de ancho "
                "y 32 px de alto (24 px para monograma)."
            )
    return ref


def groups(current, previous):
    from .review_changes import equivalent

    rows = []

    def display(key, val):
        if key in SLOTS:
            return (
                f"foto {val['asset']}"
                if val
                else "Sin imagen (se usa la de cada página)"
                if key == "sharing"
                else "Ícono original"
                if key == "icon"
                else "Logo original"
            )
        if key.endswith("scale"):
            return f"{val} %"
        return {
            "ninna": "Ninna (oficial)",
            "cormorant": "Cormorant Garamond",
            "inter": "Inter",
        }.get(val, val)

    for key, label in LABELS.items():
        before, after = previous.get(key, DEFAULT[key]), current.get(key, DEFAULT[key])
        if not equivalent(before, after):
            rows.append(
                {
                    "label": label,
                    "before_color": before if key in COLORS else "",
                    "after_color": after if key in COLORS else "",
                    "before": display(key, before),
                    "after": display(key, after),
                }
            )
    return [{"name": "Identidad de marca", "icon": "palette", "rows": rows}] if rows else []


@transaction.atomic
def publish(actor, request=None, note="", *, expected_version=None):
    require_capability(actor, "publish")
    doc = lock_document(KEY)
    check_version(doc, expected_version, publishing=True)
    if len(note) > 300:
        raise ValidationError("La nota puede tener hasta 300 caracteres.")
    value = validate(doc.brand_identity, publishing=True)
    latest = doc.brand_publication
    if latest is None or groups(value, latest.snapshot):
        latest = BrandPublication.objects.create(
            snapshot=value, note=note, published_by=actor, published_by_repr=actor.get_username()
        )
        record("cms.brand_published", actor=actor, obj=latest, request=request)
    doc.brand_publication = latest
    doc.published_version = doc.draft_version
    doc.save(update_fields=["brand_publication", "published_version"])
    return latest


@transaction.atomic
def restore(publication, actor, request=None, *, expected_version=None):
    require_capability(actor, "restore")
    doc = lock_document(KEY)
    check_version(doc, expected_version)
    doc.brand_identity = validate(publication.snapshot)
    doc.draft_version += 1
    doc.updated_by = actor
    doc.save(update_fields=["brand_identity", "draft_version", "updated_by", "updated_at"])
    DraftRevision.objects.create(
        document=doc,
        draft_version=doc.draft_version,
        snapshot=deepcopy(doc.brand_identity),
        restored_from_brand=publication,
        published_by=actor,
        published_by_repr=actor.get_username(),
    )
    record("cms.brand_restored", actor=actor, obj=publication, request=request)


def public_identity(locale="es", preview=False):
    from .media import resolve

    doc = ContentDocument.objects.select_related("brand_publication").filter(key=KEY).first()
    value = deepcopy(
        doc.brand_identity
        if doc and preview
        else doc.brand_publication.snapshot
        if doc and doc.brand_publication
        else DEFAULT
    )
    refs = {key: value[key] for key in SLOTS if value[key]}
    assets = (
        {a.pk: a for a in MediaAsset.objects.filter(pk__in={r["asset"] for r in refs.values()})}
        if refs
        else {}
    )
    for key, ref in refs.items():
        asset = assets[ref["asset"]]
        generation = asset.versions[str(ref["version"])]
        if key == "sharing":
            value[key] = resolve(ref, locale, asset=asset)
        elif key == "icon":
            value[key] = {
                size: default_storage.url(path) for size, path in generation["brand_icons"].items()
            }
        else:
            value[key] = {
                "src": default_storage.url(generation.get("brand_original", asset.original.name)),
                "width": asset.width,
                "height": asset.height,
            }
    return value


def registry():
    from dataclasses import asdict

    from .registry import Field, ImageSlot

    fields = [
        Field(key, "color", label, default=COLORS[key]) for key, label in COLOR_LABELS.items()
    ]
    fields.extend(
        [
            Field(
                "title_font",
                "select",
                "Fuente de títulos",
                options=("ninna", "cormorant"),
                option_labels=(("ninna", "Ninna (oficial)"), ("cormorant", "Cormorant Garamond")),
            ),
            Field(
                "text_font",
                "select",
                "Fuente del texto",
                options=("inter",),
                option_labels=(("inter", "Inter"),),
            ),
            *[
                Field(
                    key,
                    "select",
                    LABELS[key],
                    options=(90, 100, 110, 120),
                    option_labels=tuple((str(n), f"{n} %") for n in (90, 100, 110, 120)),
                )
                for key in ("title_scale", "text_scale")
            ],
            *[
                Field(
                    key,
                    "image",
                    label,
                    default=None,
                    help=(
                        "Logo original o PNG/WebP transparente. "
                        "SVG no se admite: puede contener scripts. "
                        "No deformar, recolorear ni añadir sombras. Deja espacio libre de una 's'. "
                        "Logotipo mínimo 32 px de alto; monograma 24 px."
                    )
                    if key not in ("sharing", "icon")
                    else "Cuadrado de al menos 512 x 512 px."
                    if key == "icon"
                    else "Foto para compartir, proporción 1.91:1.",
                )
                for key, label in SLOTS.items()
            ],
        ]
    )
    return [
        {
            "kind": "brand",
            "name": "Identidad de marca",
            "icon": "palette",
            "fields": [asdict(f) for f in fields],
            "slots": [
                asdict(ImageSlot(key, label, ratios=("1.91:1",) if key == "sharing" else ("1:1",)))
                for key, label in SLOTS.items()
            ],
            "multiple": False,
            "can_hide": False,
            "can_reorder": False,
        }
    ]
