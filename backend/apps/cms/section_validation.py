"""Mapeo de las columnas heredadas al contrato editorial del registro."""

from django.core.exceptions import ValidationError

from .registry import get_type, validate_fields, validate_props


def validate_instance(obj):
    spec = get_type(obj.kind, obj.schema_version)
    if spec.storage != "columns":
        obj.props = validate_props(obj.kind, obj.props, obj.schema_version)
        return
    if obj.props:
        raise ValidationError(
            {"props": "Este tipo usa sus campos del formulario, no contenido JSON."}
        )
    # The registry selects relevant columns. Hidden historical columns are retained
    # in snapshots for lossless restoration, but no longer written from a form.
    for field in spec.fields:
        if field.translated:
            validate_fields(
                (field,),
                {
                    field.key: {
                        lang: getattr(obj, f"{field.key}_{lang}", "") or "" for lang in ("es", "en")
                    }
                },
            )
        elif field.type == "image" and obj.image and not obj.image_reference:
            from .registry import text

            validate_fields(
                (text("alt", "Texto alternativo", 300, required=True),),
                {
                    "alt": {
                        lang: getattr(obj, f"image_alt_{lang}", "") or "" for lang in ("es", "en")
                    }
                },
                prefix="image.",
            )
        elif field.type == "collection" and not obj.collection_id:
            raise ValidationError({"collection": "Selecciona una colección para esta sección."})
    if any(field.key == "cta" for field in spec.fields):
        from .registry import validate_cta

        if obj.cta_kind != "none":
            value = {
                "kind": obj.cta_kind,
                "label": {
                    lang: getattr(obj, f"cta_label_{lang}", "") or obj.cta_label_es or ""
                    for lang in ("es", "en")
                },
            }
            if obj.cta_kind == "external":
                value["url"] = obj.cta_external_url
            elif obj.cta_kind in {"category", "stone", "collection", "piece", "page"}:
                value["target"] = getattr(obj, f"cta_{obj.cta_kind}_id")
            try:
                validate_cta(value)
            except ValidationError as exc:
                raise ValidationError({"cta_label": exc.messages}) from exc


def reject_irrelevant_columns(obj):
    """No new irrelevant values; retain any historical source for lossless restore."""
    from .models import HomeSection

    spec = get_type(obj.kind, obj.schema_version)
    keys = {field.key for field in spec.fields} if spec.storage == "columns" else set()
    candidates = {}
    for group, names in {
        "title": ("title_es", "title_en"),
        "subtitle": ("subtitle_es", "subtitle_en"),
        "body": ("body_es", "body_en"),
        "image": ("image", "image_alt_es", "image_alt_en"),
        "collection": ("collection_id",),
        "cta": (
            "cta_label_es",
            "cta_label_en",
            "cta_category_id",
            "cta_stone_id",
            "cta_collection_id",
            "cta_piece_id",
            "cta_page_id",
            "cta_external_url",
        ),
    }.items():
        if group not in keys:
            candidates.update({name: getattr(obj, name) for name in names if getattr(obj, name)})
    if "cta" not in keys and obj.cta_kind != "none":
        candidates["cta_kind"] = obj.cta_kind
    if not candidates:
        return
    previous = HomeSection.objects.filter(pk=obj.pk).first() if obj.pk else None
    errors = {
        key: "Este campo no pertenece a esta sección."
        for key, value in candidates.items()
        if previous is None or getattr(previous, key) != value
    }
    if errors:
        raise ValidationError(errors)
