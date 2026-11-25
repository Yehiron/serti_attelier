"""Contrato editorial único. No acepta HTML, estilos ni propiedades arbitrarias.

Los tipos históricos conservan sus columnas; los nuevos usan props. Personaliza
adapta sus modelos existentes, sin guardar una segunda copia del contenido.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

FieldType = Literal[
    "color",
    "short_text",
    "long_text",
    "markdown",
    "cta",
    "image",
    "list",
    "boolean",
    "select",
    "collection",
    "category",
    "piece",
]


@dataclass(frozen=True)
class Field:
    key: str
    type: FieldType
    label: str
    help: str = ""
    required: bool = False
    translated: bool = False
    min: int | None = None
    max: int | None = None
    default: Any = ""
    options: tuple[str | int, ...] = ()
    fields: tuple[Field, ...] = ()
    sortable: bool = False
    option_labels: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ImageSlot:
    key: str
    label: str
    desktop: str = "4:5 · 1600 x 2000 px"
    mobile: str = "4:5 · 1080 x 1350 px"
    alt_required: tuple[str, ...] = ("es", "en")
    ratios: tuple[str, ...] = ("16:9", "4:5", "1:1")


SEO_SLOT = ImageSlot(
    "image",
    "Foto para compartir",
    "1.91:1 · 1200 x 628 px",
    "1.91:1 · 1200 x 628 px",
    ratios=("1.91:1",),
)


@dataclass(frozen=True)
class SectionType:
    kind: str
    name: str
    description: str
    icon: str
    fields: tuple[Field, ...]
    public_fields: tuple[tuple[str, str], ...]
    slots: tuple[ImageSlot, ...] = ()
    schema_version: int = 1
    can_hide: bool = True
    can_reorder: bool = True
    multiple: bool = True
    documents: tuple[str, ...] = ("home",)
    storage: str = "columns"


def text(key, label, max=300, *, required=False, type="short_text"):
    return Field(
        key,
        type,
        label,
        help=f"Hasta {max} caracteres por idioma (ES/EN).",
        required=required,
        translated=True,
        max=max,
        default={"es": "", "en": ""},
    )


TITLE = text("title", "Título")
SUBTITLE = text("subtitle", "Subtítulo", 2000, type="long_text")
BODY = text("body", "Texto", 10000, type="long_text")
CTA = Field(
    "cta", "cta", "Enlace", "Elige un destino del sitio o una dirección HTTPS.", default=None
)
IMAGE = Field("image", "image", "Imagen", default=None)
PUB_IMAGE = (("image", "Image | null"), ("cta", "Cta | null"))
PUB_TITLE = (("title", "string"),)
STEP_FIELDS = (text("title", "Paso", 60, required=True), text("description", "Descripción", 240))
FAQ_FIELDS = (
    text("question", "Pregunta", 160, required=True),
    text("answer", "Respuesta", 1500, required=True, type="markdown"),
)


def legacy(kind, name, description, icon, fields, public, slots=()):
    return SectionType(kind, name, description, icon, fields, PUB_TITLE + public, slots)


REGISTRY: dict[str, SectionType] = {
    s.kind: s
    for s in (
        legacy(
            "hero",
            "Portada",
            "Fotos para computador y celular con título y enlace.",
            "panorama",
            (
                TITLE,
                SUBTITLE,
                IMAGE,
                CTA,
                Field(
                    "slides",
                    "list",
                    "Diapositivas",
                    sortable=True,
                    default=[],
                    fields=(
                        Field(
                            "device",
                            "select",
                            "Dispositivo",
                            options=("desktop", "mobile"),
                            option_labels=(("desktop", "Computador"), ("mobile", "Celular")),
                            default="desktop",
                        ),
                        Field("image", "image", "Foto", required=True),
                    ),
                ),
            ),
            (("subtitle", "string"), *PUB_IMAGE, ("slides?", "HeroSlide[]")),
            (
                ImageSlot("image", "Foto de respaldo", "16:9 · 2400 x 1350 px"),
                ImageSlot("slides.desktop", "Fotos para computador", "16:9 · 2400 x 1350 px"),
                ImageSlot("slides.mobile", "Fotos para celular"),
            ),
        ),
        legacy(
            "statement",
            "Manifiesto",
            "Título y texto de la marca.",
            "format_quote",
            (TITLE, BODY),
            (("body", "string"),),
        ),
        legacy(
            "stone_panels",
            "Piedras",
            "Muestra las piedras del catálogo vigente.",
            "diamond",
            (TITLE, SUBTITLE),
            (("subtitle", "string"), ("stones", "StonePanel[]")),
        ),
        legacy(
            "collection_rail",
            "Colección",
            "Carrusel de piezas de una colección vigente.",
            "view_carousel",
            (TITLE, SUBTITLE, Field("collection", "collection", "Colección", required=True)),
            (
                ("subtitle", "string"),
                ("collection", "Named & { href: string }"),
                ("pieces", "PieceCard[]"),
            ),
        ),
        *(
            legacy(
                kind,
                name,
                "Foto, título, texto y enlace opcional.",
                icon,
                (TITLE, BODY, IMAGE, CTA),
                (("body", "string"), *PUB_IMAGE),
                (ImageSlot("image", "Foto"),),
            )
            for kind, name, icon in (
                ("story", "Historia", "auto_stories"),
                ("personalize", "Personalización", "design_services"),
                ("banner", "Banner", "view_day"),
            )
        ),
        legacy(
            "category_grid",
            "Categorías",
            "Categorías vigentes, con título y subtítulo.",
            "grid_view",
            (TITLE, SUBTITLE),
            (
                ("subtitle", "string"),
                ("categories", "(Named & { href: string; count: number; image: Image | null })[]"),
            ),
        ),
        SectionType(
            "image_text",
            "Imagen con texto",
            "Una imagen junto a una historia breve.",
            "image",
            (
                text("eyebrow", "Antetítulo", 120),
                text("title", "Título", required=True),
                text("body", "Texto", 10000, required=True, type="long_text"),
                Field("image", "image", "Imagen para computador", required=True, default=None),
                Field("mobile_image", "image", "Imagen para celular", default=None),
                CTA,
                Field(
                    "image_position",
                    "select",
                    "Posición de la imagen",
                    default="left",
                    options=("left", "right"),
                    option_labels=(("left", "Izquierda"), ("right", "Derecha")),
                ),
            ),
            (
                *PUB_TITLE,
                ("eyebrow", "string"),
                ("body", "string"),
                ("image", "Image"),
                ("mobile_image", "Image | null"),
                ("cta", "Cta | null"),
                ("image_position", "'left' | 'right'"),
            ),
            (
                ImageSlot("image", "Imagen para computador"),
                ImageSlot("mobile_image", "Imagen para celular"),
            ),
            storage="props",
        ),
        SectionType(
            "faq",
            "Preguntas frecuentes",
            "Respuestas desplegables; puedes usar Markdown.",
            "quiz",
            (
                text("title", "Título", 120, required=True),
                Field(
                    "items",
                    "list",
                    "Preguntas",
                    required=True,
                    min=1,
                    max=20,
                    default=[],
                    fields=FAQ_FIELDS,
                    sortable=True,
                ),
            ),
            (*PUB_TITLE, ("items", "{ question: string; answer_html: string }[]")),
            documents=("home", "page:personalize"),
            storage="props_or_page_models",
        ),
        SectionType(
            "process",
            "Proceso de encargo",
            "Pasos ordenados para encargar una joya.",
            "format_list_numbered",
            (
                text("title", "Título", 120, required=True),
                Field(
                    "steps",
                    "list",
                    "Pasos",
                    required=True,
                    min=2,
                    max=8,
                    default=[],
                    fields=STEP_FIELDS,
                    sortable=True,
                ),
            ),
            (*PUB_TITLE, ("steps", "{ title: string; description: string }[]")),
            documents=("home", "page:personalize"),
            storage="props_or_page_models",
        ),
    )
}


def get_type(kind: str, schema_version: int = 1, document: str = "home") -> SectionType:
    spec = REGISTRY.get(kind) if isinstance(kind, str) else None
    if not spec:
        raise ValidationError({"kind": "Selecciona un tipo de sección conocido."})
    if type(schema_version) is not int or schema_version != spec.schema_version:
        raise ValidationError({"schema_version": "Esta versión de sección no es compatible."})
    if document not in spec.documents:
        raise ValidationError({"kind": "Esta sección no pertenece a este documento."})
    return spec


def _https(value):
    URLValidator(schemes=["https"])(value)


def validate_cta(value):
    from apps.catalog.models import Category, Collection, Piece, Stone

    from .models import Page

    if not isinstance(value, dict) or set(value) - {"kind", "label", "target", "url"}:
        raise ValidationError("El enlace contiene campos no permitidos.")
    labels = value.get("label")
    validate_fields((text("label", "Texto del enlace", 150, required=True),), {"label": labels})
    kind = value.get("kind")
    if not isinstance(kind, str):
        raise ValidationError("Selecciona un destino válido para el enlace.")
    models = {
        "category": Category,
        "collection": Collection,
        "piece": Piece,
        "stone": Stone,
        "page": Page,
    }
    if kind in models:
        if set(value) != {"kind", "label", "target"} or type(value["target"]) is not int:
            raise ValidationError("Selecciona el destino del enlace.")
        rows = models[kind]._default_manager.filter(pk=value["target"])
        if kind == "page":
            rows = rows.filter(kind__in=("terms", "privacy", "returns", "shipping", "cookies"))
        if not rows.exists():
            raise ValidationError("El destino seleccionado no existe o no es una página legal.")
    elif kind == "external":
        if set(value) != {"kind", "label", "url"}:
            raise ValidationError("Escribe un enlace HTTPS.")
        _https(value["url"])
    elif kind in {"catalog", "personalize", "story", "contact"}:
        if set(value) != {"kind", "label"}:
            raise ValidationError("Este destino no admite campos adicionales.")
    else:
        raise ValidationError("Selecciona un destino válido para el enlace.")
    return deepcopy(value)


def validate_image(value):
    if isinstance(value, dict) and "asset" in value:
        from .media import validate_reference

        return validate_reference(value)
    if not isinstance(value, dict) or set(value) != {"src", "srcset", "width", "height", "alt"}:
        raise ValidationError("La imagen debe incluir archivo, medidas y texto alternativo ES/EN.")
    for name in ("src", "srcset"):
        if not isinstance(value[name], str):
            raise ValidationError("La dirección de la imagen no es válida.")
    src = value["src"]
    if not (src.startswith("/") and not src.startswith(("//", "/\\"))):
        _https(src)
    if any(c in src for c in ("\\", "\n", "\r", "\x00")) or urlsplit(src).fragment:
        raise ValidationError("La dirección de la imagen no es válida.")
    # Renditions are generated by the image pipeline; arbitrary srcsets are never authored.
    if value["srcset"]:
        raise ValidationError("Las versiones de imagen se generan al cargar el archivo.")
    if any(type(value[k]) is not int or value[k] <= 0 for k in ("width", "height")):
        raise ValidationError("La imagen necesita medidas mayores que cero.")
    validate_fields((text("alt", "Texto alternativo", 300, required=True),), {"alt": value["alt"]})
    return deepcopy(value)


def validate_fields(fields: tuple[Field, ...], values: Any, prefix: str = "") -> dict[str, Any]:
    if not isinstance(values, dict):
        raise ValidationError({prefix or "props": "Escribe los campos de la sección."})
    errors: dict[str, Any] = {
        f"{prefix}{key}": "Este campo no pertenece a esta sección."
        for key in values.keys() - {f.key for f in fields}
    }
    result: dict[str, Any] = {}
    for field in fields:
        key = f"{prefix}{field.key}"
        value = values.get(field.key, deepcopy(field.default))
        try:
            if field.type in {"short_text", "long_text", "markdown"}:
                translations = value if field.translated else {"es": value}
                if not isinstance(translations, dict) or set(translations) - {"es", "en"}:
                    raise ValidationError("Escribe el texto en español e inglés.")
                normalized = {}
                for locale in ("es", "en") if field.translated else ("es",):
                    content = translations.get(locale, "")
                    if not isinstance(content, str):
                        errors[f"{key}.{locale}"] = "Escribe un texto."
                        continue
                    if field.required and not content.strip():
                        errors[f"{key}.{locale}"] = "Este campo es obligatorio."
                    if field.max is not None and len(content) > field.max:
                        errors[f"{key}.{locale}"] = f"Usa como máximo {field.max} caracteres."
                    if field.min is not None and len(content) < field.min:
                        errors[f"{key}.{locale}"] = f"Usa al menos {field.min} caracteres."
                    normalized[locale] = content
                result[field.key] = normalized if field.translated else normalized.get("es", "")
            elif field.type == "list":
                if not isinstance(value, list):
                    raise ValidationError("Escribe una lista ordenada.")
                if field.min is not None and len(value) < field.min:
                    raise ValidationError(f"Agrega al menos {field.min} elementos.")
                if field.max is not None and len(value) > field.max:
                    raise ValidationError(f"Usa como máximo {field.max} elementos.")
                result[field.key] = [
                    validate_fields(field.fields, row, f"{key}.{i}.") for i, row in enumerate(value)
                ]
            elif field.type in {"image", "cta"}:
                if value is None:
                    if field.required:
                        raise ValidationError("Este campo es obligatorio.")
                    result[field.key] = None
                else:
                    result[field.key] = (validate_image if field.type == "image" else validate_cta)(
                        value
                    )
            elif field.type == "select":
                if value not in field.options:
                    raise ValidationError("Selecciona una de las opciones disponibles.")
                result[field.key] = value
            elif field.type == "boolean":
                if type(value) is not bool:
                    raise ValidationError("Selecciona sí o no.")
                result[field.key] = value
            else:
                from apps.catalog.models import Category, Collection, Piece

                model = {"collection": Collection, "category": Category, "piece": Piece}[field.type]
                if type(value) is not int or not model._default_manager.filter(pk=value).exists():
                    raise ValidationError("Selecciona un elemento existente del catálogo.")
                result[field.key] = value
        except ValidationError as exc:
            if hasattr(exc, "message_dict"):
                if field.type in {"image", "cta"}:
                    errors.update(
                        {f"{key}.{path}": messages for path, messages in exc.message_dict.items()}
                    )
                else:
                    errors.update(exc.message_dict)
            else:
                errors[key] = exc.messages
    if errors:
        raise ValidationError(errors)
    return result


def validate_props(kind, props, schema_version=1, document="home"):
    return validate_fields(get_type(kind, schema_version, document).fields, props)


def export_registry():
    from .brand import registry as brand_registry

    return {
        "brand_document": brand_registry()[0],
        "registry_version": 1,
        "locales": ["es", "en"],
        "sections": [asdict(spec) for spec in REGISTRY.values()],
        "seo_slot": asdict(SEO_SLOT),
        "page_bindings": {
            "page:personalize": {
                "process": {
                    "title_field": "process_title",
                    "relation": "process_steps",
                    "list_field": "steps",
                    "model": "cms.ProcessStep",
                    "can_hide": False,
                    "can_reorder": False,
                    "multiple": False,
                },
                "faq": {
                    "title_field": "faq_title",
                    "relation": "faq_items",
                    "list_field": "items",
                    "model": "cms.FaqItem",
                    "can_hide": False,
                    "can_reorder": False,
                    "multiple": False,
                },
            }
        },
        "cta_destinations": {
            **{
                key: {"target": "catalog." + model}
                for key, model in (
                    ("category", "Category"),
                    ("collection", "Collection"),
                    ("piece", "Piece"),
                    ("stone", "Stone"),
                )
            },
            "page": {"target": "cms.Page", "legal_only": True},
            **{key: {} for key in ("catalog", "personalize", "story", "contact")},
            "external": {"url_scheme": "https"},
        },
    }


def typescript_contract():
    lines = [
        "// Generado por manage.py export_section_registry --typescript. No editar.",
        "import type { Image, Cta, HeroSlide, Named, StonePanel, PieceCard } from './types';",
        "export type MediaReference = { asset: number; crop: "
        + " | ".join(
            repr(ratio)
            for ratio in dict.fromkeys(
                ratio
                for slot in [SEO_SLOT, *(slot for spec in REGISTRY.values() for slot in spec.slots)]
                for ratio in slot.ratios
            )
        )
        + "; version: number };",
        "export type Section = { id: string | number; schema_version: 1 } & (",
    ]
    for spec in REGISTRY.values():
        fields = "; ".join(f"{key}: {value}" for key, value in spec.public_fields)
        lines.append(f"  | {{ kind: '{spec.kind}'; {fields} }}")
    kinds = ", ".join(repr(spec.kind) for spec in REGISTRY.values())
    return "\n".join([*lines, ");", f"export const sectionKinds = [{kinds}] as const;", ""])


def editorial_props(kind, props):
    """Readable audit values, preserving translations and order without exposing JSON."""
    result = {}

    def visit(fields, values, prefix=""):
        for field in fields:
            value = values.get(field.key, field.default)
            label = prefix + field.label
            if field.translated:
                for lang, name in (("es", "español"), ("en", "inglés")):
                    result[f"{label} ({name})"] = (value or {}).get(lang, "")
            elif field.type == "list":
                for i, row in enumerate(value):
                    visit(field.fields, row, f"{label} {i + 1} · ")
            elif field.type == "image":
                if value and "asset" in value:
                    result[label] = (
                        f"Foto de biblioteca {value['asset']} · {value['crop']} "
                        f"· versión {value['version']}"
                    )
                    continue
                result[label] = value["src"] if value else "Sin foto"
                for lang, name in (("es", "español"), ("en", "inglés")):
                    result[f"{label} · Texto alternativo ({name})"] = (
                        value["alt"][lang] if value else ""
                    )
            elif field.type == "cta":
                for lang, name in (("es", "español"), ("en", "inglés")):
                    result[f"{label} ({name})"] = value["label"][lang] if value else ""
                result[f"{label} · Destino"] = (
                    f"{value['kind']}: {value.get('url', value.get('target', ''))}"
                    if value
                    else "Sin enlace"
                )
            else:
                result[label] = dict(field.option_labels).get(value, value)

    spec = REGISTRY.get(kind)
    if spec:
        visit(spec.fields, props)
    return result
