"""Presentación española de eventos; no expone direcciones IP ni datos de sesión."""

import json

from django.template.response import TemplateResponse

ACTIONS = {
    "catalog.piece_updated": "Pieza guardada",
    "catalog.piece_published": "Pieza publicada",
    "catalog.piece_hidden": "Pieza ocultada",
    "catalog.piece_archived": "Pieza archivada",
    "catalog.piece_duplicated": "Pieza duplicada",
    "catalog.piece_deleted": "Pieza eliminada",
    "catalog.relations_updated": "Clasificación actualizada",
    "catalog.collections_updated": "Colecciones actualizadas",
    "catalog.photos_updated": "Fotos actualizadas",
}
LABELS = {
    "principal": "Foto principal cambiada",
    "hover": "Foto al pasar el mouse cambiada",
    "orden": "Orden de fotos",
    "borradas": "Fotos eliminadas",
    "source": "Pieza de origen",
    "status": "Publicación",
    "sale_state": "Estado de venta",
    "category": "Categoría",
}
VALUES = {
    "published": "Publicada",
    "draft": "Borrador",
    "hidden": "Oculta",
    "archived": "Archivada",
    "available": "Disponible",
    "reserved": "Reservada",
    "sold": "Vendida",
    "preorder": "Preventa",
}


def readable(value):
    if value is None or value == "" or value == []:
        return "Sin valor"
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if isinstance(value, list):
        return ", ".join(readable(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return VALUES.get(str(value), str(value))


# Internal bookkeeping that means nothing to the shop owner.
HIDDEN_KEYS = {"id", "position", "slug", "slug_es", "slug_en"}
PHOTO_KEYS = {"principal", "hover", "orden", "borradas"}
MONEY_KEYS = {"price_cents": "Precio", "sale_price_cents": "Precio rebajado"}
DATE_KEYS = {"published_at", "sold_at"}
ATTRIBUTE_LABELS = {
    "metal": "Metal",
    "metal_purity": "Pureza",
    "ring_size": "Talla",
    "length_mm": "Largo (mm)",
    "dimensions_mm": "Dimensiones (mm)",
    "weight_g": "Peso (g)",
    "carats": "Quilates",
}


def _photo_name(pk, photos):
    """«Foto 2 (Anillo de frente)» instead of a database id."""
    photo = photos.get(pk)
    if photo is None:
        return "una foto eliminada"
    alt = getattr(photo, "alt_es", "") or getattr(photo, "alt", "")
    label = f"Foto {photo.position + 1}"
    return f"{label} ({alt})" if alt else label


def _value(key, value, photos):
    from apps.core.formatting import format_admin_cop, format_bogota_datetime

    if value is None or value == "" or value == [] or value == {}:
        return "Sin valor"
    if key in PHOTO_KEYS:
        items = value if isinstance(value, list) else [value]
        return ", ".join(_photo_name(item, photos) for item in items)
    if key in MONEY_KEYS and isinstance(value, int):
        return format_admin_cop(value)
    if key in DATE_KEYS and isinstance(value, str):
        from django.utils.dateparse import parse_datetime

        parsed = parse_datetime(value)
        return format_bogota_datetime(parsed, "es") if parsed else value
    if key == "category" and isinstance(value, int):
        from .models import Category

        category = Category.objects.select_related("parent").filter(pk=value).first()
        if category is None:
            return "una categoría eliminada"
        return f"{category.parent} → {category}" if category.parent_id else str(category)
    if key == "attributes" and isinstance(value, dict):
        return ", ".join(
            f"{ATTRIBUTE_LABELS.get(name, name)}: {readable(item)}" for name, item in value.items()
        )
    return readable(value)


def describe_event(event):
    from .models import Piece, PieceImage

    labels = {field.name: str(field.verbose_name) for field in Piece._meta.concrete_fields}
    labels.update(MONEY_KEYS)
    title = ACTIONS.get(event.action)
    if title is None:
        noun = {
            "category": "Categoría",
            "stone": "Piedra",
            "material": "Material",
            "collection": "Colección",
        }
        model, _, operation = event.action.removeprefix("catalog.").partition("_")
        verb = {"created": "creación", "updated": "actualización", "deleted": "eliminación"}
        title = f"{noun.get(model, 'Contenido')}: {verb.get(operation, 'cambio')}"
    diff = event.diff or {}
    photo_ids = set()
    for key in PHOTO_KEYS & diff.keys():
        for side in diff[key]:
            photo_ids.update(side if isinstance(side, list) else [side])
    photos = PieceImage.objects.in_bulk([pk for pk in photo_ids if isinstance(pk, int)])
    lines = []
    for key, pair in diff.items():
        # modeltranslation mirrors the Spanish value in the base field; show only "[es]".
        if key in HIDDEN_KEYS or f"{key}_es" in diff:
            continue
        before, after = _value(key, pair[0], photos), _value(key, pair[1], photos)
        if before == after:
            continue
        lines.append(f"{LABELS.get(key, labels.get(key, key))}: {before} → {after}")
    return [title, *lines]


class CatalogAuditHistoryMixin:
    object_history_template = "admin/catalog/piece/object_history.html"

    def history_view(self, request, object_id, extra_context=None):
        from django.contrib.contenttypes.models import ContentType
        from django.core.paginator import Paginator

        from apps.audit.models import AuditLog

        # The inherited view keeps Django's object permissions and LogEntry history.
        response = super().history_view(request, object_id, extra_context)
        if isinstance(response, TemplateResponse):
            events = AuditLog.objects.filter(
                content_type=ContentType.objects.get_for_model(self.model), object_id=str(object_id)
            ).order_by("-at", "-pk")
            page = Paginator(events, 50).get_page(request.GET.get("audit_page"))
            response.context_data["catalog_audit_page"] = page
            response.context_data["catalog_audit_events"] = [
                {
                    "at": event.at,
                    "actor": event.actor_repr or "Sistema",
                    "description": describe_event(event),
                }
                for event in page
            ]
        return response
