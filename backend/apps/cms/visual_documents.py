"""Registry driven editor adapter. Every write shares the document transaction."""

from copy import deepcopy
from dataclasses import asdict, replace

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404

from apps.audit.services import record

from . import editor_services, services
from .models import ContentDocument, FaqItem, HeroSlide, HomeSection, Page, ProcessStep
from .registry import REGISTRY, export_registry, get_type, text, validate_fields


def merge_values(previous, patch):
    """A patch in English must never clear the existing Spanish source."""
    result = deepcopy(previous)
    for key, value in patch.items():
        result[key] = (
            {**result.get(key, {}), **value}
            if isinstance(value, dict) and isinstance(result.get(key), dict)
            else value
        )
    return result


def page_for(key):
    if not key.startswith("page:"):
        raise ValidationError("Selecciona una página válida.")
    return get_object_or_404(Page, kind=key[5:])


def translations(obj, key):
    return {lang: getattr(obj, f"{key}_{lang}", "") or "" for lang in ("es", "en")}


def values(section):
    spec = get_type(section.kind)
    if spec.storage != "columns":
        return deepcopy(section.props)
    result = {}
    for field in spec.fields:
        if field.translated:
            result[field.key] = translations(section, field.key)
        elif field.type == "collection":
            result[field.key] = section.collection_id
        elif field.type == "cta":
            result[field.key] = (
                None
                if section.cta_kind == "none"
                else {
                    "kind": section.cta_kind,
                    "label": translations(section, "cta_label"),
                    **(
                        {"url": section.cta_external_url}
                        if section.cta_kind == "external"
                        else {"target": getattr(section, f"cta_{section.cta_kind}_id")}
                        if section.cta_kind in {"category", "stone", "collection", "piece", "page"}
                        else {}
                    ),
                }
            )
        elif field.type == "image":
            result[field.key] = (
                deepcopy(section.image_reference)
                if section.image_reference
                else (
                    {"alt": translations(section, "image_alt"), "src": section.image.url}
                    if section.image
                    else None
                )
            )
    if section.kind == "hero":
        from .editor import thumbnail
        from .media import resolve

        result["slides"] = [
            {
                "id": str(slide.pk),
                "device": slide.device,
                "thumbnail": (
                    resolve(slide.image_reference, "es")["src"]
                    if slide.image_reference
                    else thumbnail(slide.renditions)
                ),
                "reference": slide.image_reference,
                "alt": translations(slide, "alt"),
            }
            for slide in section.slides.all()
        ]
    return result


def read_sections(key):
    if key.startswith("menu:"):
        return [
            {
                "id": "menu",
                "kind": "menu",
                "visible": True,
                "values": {"items": ContentDocument.objects.get(key=key).menu_items},
            }
        ]
    if key == "home":
        return [
            {"id": str(row.pk), "kind": row.kind, "visible": row.is_visible, "values": values(row)}
            for row in HomeSection.objects.prefetch_related("slides").order_by("position", "pk")
        ]
    page = page_for(key)
    result = [
        {
            "id": "page",
            "kind": "page",
            "visible": True,
            "values": {f: translations(page, f) for f in ("title", "body", "slug")},
        }
    ]
    for kind, binding in export_registry()["page_bindings"].get(key, {}).items():
        list_field = next(f for f in REGISTRY[kind].fields if f.type == "list")
        result.append(
            {
                "id": kind,
                "kind": kind,
                "visible": True,
                "values": {
                    "title": translations(page, binding["title_field"]),
                    binding["list_field"]: [
                        {f.key: translations(item, f.key) for f in list_field.fields}
                        for item in getattr(page, binding["relation"]).all()
                    ],
                },
            }
        )
    return result


def applicable_registry(key):
    specs = [asdict(spec) for spec in REGISTRY.values() if key in spec.documents]
    if key.startswith("menu:"):
        from .registry import CTA, Field

        return [
            {
                "kind": "menu",
                "name": "Enlaces del menú",
                "icon": "menu",
                "fields": [
                    asdict(
                        Field(
                            "items",
                            "list",
                            "Enlaces",
                            max=8 if key == "menu:main" else 12,
                            default=[],
                            sortable=True,
                            fields=(
                                replace(CTA, key="link", label="Enlace", max=40),
                                Field("visible", "boolean", "Mostrar enlace", default=True),
                            ),
                        )
                    )
                ],
                "multiple": False,
                "can_hide": False,
                "can_reorder": False,
            }
        ]
    if key != "home":
        page_for(key)
        specs.append(
            {
                "kind": "page",
                "name": "Contenido de la página",
                "icon": "article",
                "fields": [
                    asdict(text("title", "Título", 250, required=True)),
                    asdict(text("body", "Contenido", 50000, type="markdown")),
                    asdict(text("slug", "Dirección de la página", 250)),
                ],
                "multiple": False,
                "can_hide": False,
                "can_reorder": False,
            }
        )
        for spec in specs:
            spec.update(multiple=False, can_hide=False, can_reorder=False)
    from .registry import SEO_SLOT, Field

    specs.append(
        {
            "kind": "seo",
            "name": "Buscadores y redes sociales",
            "icon": "search",
            "fields": [
                asdict(text("title", "Título SEO", 60)),
                asdict(text("description", "Descripción SEO", 155, type="long_text")),
                asdict(Field("image", "image", "Foto para compartir", default=None)),
                asdict(Field("noindex", "boolean", "No indexar", default=False)),
            ],
            "slots": [asdict(SEO_SLOT)],
            "multiple": False,
            "can_hide": False,
            "can_reorder": False,
        }
    )
    return specs


def write_values(section, data):
    spec = get_type(section.kind)
    allowed = {f.key for f in spec.fields} - {"slides"}
    if set(data) - allowed:
        raise ValidationError({"__all__": "Hay campos que no pertenecen a esta sección."})
    if spec.storage != "columns":
        section.props = {**section.props, **data}
        return
    for field in spec.fields:
        if field.key not in data:
            continue
        value = data.get(field.key)
        if field.translated:
            for lang in ("es", "en"):
                if lang in (value or {}):
                    name = f"{field.key}_{lang}"
                    new = value[lang]
                    # Preserve historical nulls when the editor displays an empty input.
                    if (getattr(section, name) or "") != (new or ""):
                        setattr(section, name, new)
        elif field.type == "collection":
            section.collection_id = value
        elif field.type == "cta":
            from .registry import validate_cta

            if value:
                validate_cta(value)
            section.cta_kind = value["kind"] if value else "none"
            for lang in ("es", "en"):
                setattr(section, f"cta_label_{lang}", value["label"][lang] if value else "")
            section.cta_external_url = value.get("url", "") if value else ""
            for kind in ("category", "stone", "collection", "piece", "page"):
                setattr(
                    section,
                    f"cta_{kind}_id",
                    value.get("target") if value and value["kind"] == kind else None,
                )
        elif field.type == "image" and value:
            if "asset" in value:
                from .media import validate_reference

                section.image_reference = validate_reference(value)
                continue
            for lang in ("es", "en"):
                new = value.get("alt", {}).get(lang, "")
                if (getattr(section, f"image_alt_{lang}") or "") != (new or ""):
                    setattr(section, f"image_alt_{lang}", new)


def mutate(key, action, data, actor, request):
    """Caller holds edit_document, including version check, before reading any rows."""
    if action == "translation-equal":
        from .phase6_views import missing_pairs

        document = ContentDocument.objects.get(key=key)
        section = next((row for row in read_sections(key) if row["id"] == data["id"]), None)
        if data["id"] == "seo" and not key.startswith("menu:"):
            section = {"values": document.seo}
        match = (
            next(
                (
                    (path, es, en)
                    for path, es, en in missing_pairs(section["values"])
                    if path == data["path"]
                ),
                None,
            )
            if section
            else None
        )
        if not match or match[1] != match[2]:
            raise ValidationError("Solo puedes marcar textos que ya sean iguales en ambos idiomas.")
        document.translation_exemptions = {
            **document.translation_exemptions,
            f"{data['id']}.{data['path']}": match[1],
        }
        document.save(update_fields=["translation_exemptions"])
        record("cms.translation_equal", actor=actor, obj=document, request=request)
        return
    if data.get("id") == "seo":
        from .media import validate_reference
        from .page_options import validate_seo

        document = ContentDocument.objects.get(key=key)
        if action == "media-select":
            value = {"image": validate_reference(data["reference"], selecting=True)}
        elif action == "update":
            value = data["values"]
        else:
            raise ValidationError("Guarda las opciones para buscadores.")
        before = deepcopy(document.seo)
        document.seo = validate_seo(merge_values(before, value), before, actor)
        document.save(update_fields=["seo"])
        record(
            "cms.seo_saved",
            actor=actor,
            obj=document,
            request=request,
            diff={"Opciones para buscadores": [before, document.seo]},
        )
        return
    if key.startswith("menu:"):
        from .menus import validate_items

        if action != "update" or data.get("id") != "menu" or set(data["values"]) != {"items"}:
            raise ValidationError("Guarda los enlaces del menú.")
        document = ContentDocument.objects.get(key=key)
        before = deepcopy(document.menu_items)
        document.menu_items = validate_items(key, data["values"]["items"])
        document.save(update_fields=["menu_items"])
        record(
            "cms.menu_saved",
            actor=actor,
            obj=document,
            request=request,
            diff={"Enlaces": [before, document.menu_items]},
        )
        return
    if key != "home":
        if action != "update":
            raise ValidationError("Esta página tiene una estructura fija.")
        page = page_for(key)
        if data["id"] == "page":
            fields = tuple(
                text(
                    f,
                    f,
                    50000 if f == "body" else 250,
                    type="markdown" if f == "body" else "short_text",
                )
                for f in ("title", "body", "slug")
            )
            cleaned = validate_fields(
                fields,
                merge_values(
                    next(row["values"] for row in read_sections(key) if row["id"] == data["id"]),
                    data["values"],
                ),
            )
            for field, value in cleaned.items():
                for lang in ("es", "en"):
                    if (getattr(page, f"{field}_{lang}") or "") != (value[lang] or ""):
                        setattr(page, f"{field}_{lang}", value[lang])
            services.save_page(page, actor=actor, request=request)
            return
        kind = data["id"]
        binding = export_registry()["page_bindings"].get(key, {}).get(kind)
        if not binding:
            raise ValidationError("La sección no pertenece a esta página.")
        old = list(getattr(page, binding["relation"]).all())
        # Bindings retain the legacy models' incomplete translations and historic sizes.
        fields = tuple(
            replace(
                f,
                min=0,
                max=max(f.max or 0, len(old)),
                fields=tuple(replace(child, required=False) for child in f.fields),
            )
            if f.type == "list"
            else replace(f, required=False)
            for f in REGISTRY[kind].fields
        )
        cleaned = validate_fields(
            fields,
            merge_values(
                next(row["values"] for row in read_sections(key) if row["id"] == data["id"]),
                data["values"],
            ),
        )
        if "title" in data["values"]:
            for lang in ("es", "en"):
                name = f"{binding['title_field']}_{lang}"
                if (getattr(page, name) or "") != (cleaned["title"][lang] or ""):
                    setattr(page, name, cleaned["title"][lang])
            services.save_page(page, actor=actor, request=request)
        if binding["list_field"] not in data["values"]:
            return
        model = ProcessStep if kind == "process" else FaqItem
        rows = cleaned[binding["list_field"]]
        for item in old[len(rows) :]:
            services.delete_page_item(item, actor=actor, request=request)
        for position, row in enumerate(rows):
            item = old[position] if position < len(old) else model(page=page)
            item.position = position
            for field, translations_ in row.items():
                for lang, value in translations_.items():
                    if (getattr(item, f"{field}_{lang}") or "") != (value or ""):
                        setattr(item, f"{field}_{lang}", value)
            services.save_page_item(item, actor=actor, request=request)
        return
    if action == "reorder":
        editor_services.reorder_sections(
            [int(pk) for pk in data["ids"]], actor=actor, request=request
        )
        return
    if action == "create":
        get_type(data["kind"], document=key)
        section = HomeSection(kind=data["kind"], position=HomeSection.objects.count())
        write_values(section, data["values"])
        services.save_section(section, actor=actor, request=request)
        return str(section.pk)
    section = get_object_or_404(HomeSection, pk=data["id"])
    spec = get_type(section.kind)
    if action == "media-select":
        from .media import resolve, validate_reference

        ref = validate_reference(data["reference"], selecting=True)
        slot = data.get("slot", "image")
        image_slot = next((slot_ for slot_ in spec.slots if slot_.key == slot), None)
        if not image_slot or ref["crop"] not in image_slot.ratios:
            raise ValidationError("Esta foto no corresponde a esta sección.")
        if slot.startswith("slides.") and section.kind == "hero":
            device = slot.split(".")[1]
            image = resolve(ref, "es")
            slide = (
                get_object_or_404(section.slides, pk=data["slide"], device=device)
                if data.get("slide")
                else HeroSlide(section=section, device=device)
            )
            slide.image_reference = ref
            slide.width, slide.height = image["width"], image["height"]
            slide.alt_es, slide.alt_en = resolve(ref, "es")["alt"], resolve(ref, "en")["alt"]
            if not slide.pk:
                slide.position = section.slides.filter(device=device).count()
            # Keep legacy source intact for history; reference takes precedence.
            services.save_hero_slide(slide, actor=actor, request=request)
        else:
            write_values(section, {slot: ref})
            services.save_section(section, actor=actor, request=request)
        record("cms.media_selected", actor=actor, obj=section, request=request)
    elif action.startswith("hero-"):
        device = data.get("device")
        if section.kind != "hero" or device not in HeroSlide.Device.values:
            raise ValidationError("Selecciona una portada y un dispositivo válidos.")
        if action == "hero-reorder":
            editor_services.reorder_hero_slides(
                section, device, [int(pk) for pk in data["ids"]], actor=actor, request=request
            )
        elif action in {"hero-alt", "hero-delete"}:
            slide = get_object_or_404(section.slides, pk=data["slide"], device=device)
            if action == "hero-delete":
                services.delete_hero_slide(slide, actor=actor, request=request)
            else:
                alt = validate_fields(
                    (text("alt", "Texto alternativo", 300, required=True),), {"alt": data["alt"]}
                )["alt"]
                slide.alt_es, slide.alt_en = alt["es"], alt["en"]
                services.save_hero_slide(slide, actor=actor, request=request)
        else:
            raise ValidationError("Esta acción no está disponible para la portada.")
    elif action == "update":
        write_values(section, data["values"])
        services.save_section(section, actor=actor, request=request)
    elif action == "visibility" and spec.can_hide:
        if type(data["visible"]) is not bool:
            raise ValidationError("Selecciona mostrar u ocultar.")
        editor_services.set_section_visibility(
            section, data["visible"], actor=actor, request=request
        )
    elif action == "duplicate" and spec.multiple:
        slides = list(section.slides.all())
        section.pk = None
        section._state.adding = True
        section.position = HomeSection.objects.count()
        services.save_section(section, actor=actor, request=request)
        for slide in slides:
            slide.pk = None
            slide.section = section
            services.save_hero_slide(slide, actor=actor, request=request)
        record("cms.section_duplicated", actor=actor, obj=section, request=request)
        return str(section.pk)
    elif action == "delete":
        record(
            "cms.section_deleted",
            actor=actor,
            obj=section,
            request=request,
            diff={"Sección": [spec.name, "Eliminada del borrador"]},
        )
        section.delete()
    else:
        raise ValidationError("Esta acción no está disponible para la sección.")
