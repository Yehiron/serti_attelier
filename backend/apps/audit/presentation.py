"""Presentación legible de eventos inmutables de auditoría."""

import contextlib
import re
from decimal import Decimal, InvalidOperation

from django.core.exceptions import FieldDoesNotExist

# Cada entrada contiene verbo, módulo e icono. El objeto se añade por separado.
ACTIONS = {}


def _add(module, icon, entries):
    for action, verb in entries.items():
        ACTIONS[action] = {"verb": verb, "module": module, "icon": icon}


_add(
    "Catálogo",
    "◆",
    {
        "catalog.piece_created": "creó la pieza",
        "catalog.piece_updated": "actualizó la pieza",
        "catalog.piece_published": "publicó la pieza",
        "catalog.piece_deleted": "eliminó la pieza",
        "catalog.piece_hidden": "ocultó la pieza",
        "catalog.piece_archived": "archivó la pieza",
        "catalog.piece_duplicated": "duplicó la pieza",
        "catalog.relations_updated": "actualizó las relaciones de la pieza",
        "catalog.photos_updated": "actualizó las fotos de la pieza",
        "catalog.collections_updated": "actualizó las colecciones de la pieza",
        "catalog.collection_curated": "organizó la colección",
        "inventory.cancelled_piece_released": "liberó la pieza del pedido cancelado",
        "inventory.cancelled_piece_retained": "retuvo la pieza del pedido cancelado",
    },
)
for kind, noun in (
    ("category", "categoría"),
    ("stone", "piedra"),
    ("material", "material"),
    ("collection", "colección"),
):
    for suffix, verb in (("created", "creó"), ("updated", "actualizó"), ("deleted", "eliminó")):
        ACTIONS[f"catalog.{kind}_{suffix}"] = {
            "verb": f"{verb} {('el' if kind == 'material' else 'la')} {noun}",
            "module": "Catálogo",
            "icon": "◆",
        }
_add(
    "Pedidos",
    "▣",
    {
        "orders.created": "creó el pedido",
        "orders.status_changed": "cambió el estado del pedido",
        "orders.cancelled": "canceló el pedido",
        "orders.note_added": "añadió una nota al pedido",
        "orders.exported": "exportó el pedido",
        "orders.incident_opened": "abrió una incidencia del pedido",
        "orders.incident_resolved": "resolvió una incidencia del pedido",
    },
)
_add(
    "Pagos",
    "$",
    {
        "payments.approved": "aprobó el pago del pedido",
        "payments.declined": "rechazó el pago del pedido",
        "payments.pending": "registró un pago pendiente",
        "payments.error": "registró un error de pago",
        "payments.mismatch": "detectó una discrepancia en el pago",
        "payments.voided": "anuló el pago",
    },
)
_add(
    "Página web",
    "▤",
    {
        "cms.draft_saved": "guardó el borrador",
        "cms.home_published": "publicó la portada",
        "cms.home_restored": "restauró la portada",
        "cms.page_published": "publicó la página",
        "cms.page_restored": "restauró la página",
        "cms.menu_published": "publicó el menú",
        "cms.menu_restored": "restauró el menú",
        "cms.menu_saved": "guardó el menú",
        "cms.brand_published": "publicó la identidad de marca",
        "cms.brand_restored": "restauró la identidad de marca",
        "cms.brand_saved": "guardó la identidad de marca",
        "cms.seo_saved": "guardó el SEO",
        "cms.slide_deleted": "eliminó la diapositiva",
        "cms.slides_uploaded": "subió diapositivas",
        "cms.slides_reordered": "reordenó las diapositivas",
        "cms.sections_reordered": "reordenó las secciones",
        "cms.section_deleted": "eliminó la sección",
        "cms.section_duplicated": "duplicó la sección",
        "cms.page_item_deleted": "eliminó el elemento de la página",
        "cms.redirect_saved": "guardó la redirección",
        "cms.piece_redirects_updated": "actualizó las redirecciones de la pieza",
        "cms.translation_equal": "registró una traducción igual",
    },
)
_add(
    "Fotos",
    "▧",
    {
        "cms.media_saved": "guardó la foto",
        "cms.media_uploaded": "subió la foto",
        "cms.media_selected": "seleccionó la foto",
        "cms.media_archived": "archivó la foto",
        "cms.media_deleted": "eliminó la foto",
        "cms.editor_photo_uploaded": "subió una foto al editor",
        "cms.media_orphan_removed": "eliminó la foto sin uso",
        "cms.media_file_deleted": "eliminó el archivo de foto",
    },
)
_add(
    "Mensajes",
    "✉",
    {
        "inquiries.answered": "marcó como respondido el mensaje",
        "inquiries.archived": "archivó el mensaje",
        "inquiries.status_changed": "cambió el estado del mensaje",
        "notifications.copied": "copió la notificación",
        "notifications.resent": "reenvió la notificación",
    },
)
_add(
    "Promociones",
    "%",
    {
        "promotions.created": "creó la promoción",
        "promotions.updated": "actualizó la promoción",
        "promotions.deactivated": "desactivó la promoción",
        "promotions.deleted": "eliminó la promoción",
    },
)
_add("Datos del sitio", "⚙", {"core.settings_updated": "actualizó los datos del sitio"})
_add(
    "Equipo y accesos",
    "♙",
    {
        "accounts.user_created": "creó el usuario",
        "accounts.user_updated": "actualizó el usuario",
        "accounts.user_deleted": "eliminó el usuario",
        "accounts.access_changed": "cambió los permisos de acceso",
        "accounts.role_permissions_changed": "cambió los permisos del rol",
        "auth.login": "inició sesión",
        "auth.logout": "cerró sesión",
        "auth.login_failed": "intentó iniciar sesión sin éxito",
        "auth.2fa_failed": "falló la verificación en dos pasos",
        "auth.2fa_enabled": "activó la verificación en dos pasos",
        "auth.2fa_removed": "quitó la verificación en dos pasos",
        "auth.locked_out": "bloqueó el acceso",
        "auth.password_changed": "cambió la contraseña",
        "auth.password_reset_requested": "solicitó restablecer la contraseña",
    },
)
ACTION_LABELS = {key: value["verb"].capitalize() for key, value in ACTIONS.items()}
MODULES = tuple(dict.fromkeys(item["module"] for item in ACTIONS.values()))


def is_test(entry):
    actor = (entry.actor_repr or "").lower()
    obj = (entry.object_repr or "").lower()
    marker = re.compile(r"(^|[^a-z0-9])(e2e|prueba)([^a-z0-9]|$)")
    return bool(
        actor.startswith("e2e-")
        or re.search(r"(^|[^a-z0-9])e2e([^a-z0-9]|$)", actor)
        or marker.search(obj)
    )


def who(entry):
    if is_test(entry):
        return "Prueba automática"
    if entry.actor_id:
        return (
            entry.actor.get_full_name()
            or entry.actor.get_username()
            or entry.actor_repr
            or "Sistema"
        )
    return entry.actor_repr or "Sistema"


def describe(entry):
    action = ACTIONS.get(entry.action)
    if not action:
        readable = entry.action.replace(".", " · ").replace("_", " ")
        return f"{who(entry)} · Acción registrada: {readable}"
    return " ".join(part for part in (who(entry), action["verb"], entry.object_repr or "") if part)


def _value(value, field):
    if value == "[redactado]":
        return "(oculto por seguridad)"
    if value is None or value == "":
        return "Vacío"
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if isinstance(value, list):
        return ", ".join(_value(item, "") for item in value) or "Vacío"
    if field.endswith("_cents"):
        try:
            pesos = Decimal(str(value)) / 100
            formatted = f"{pesos:,.2f}".rstrip("0").rstrip(".")
            return "$ " + formatted.replace(",", "_").replace(".", ",").replace("_", ".")
        except (InvalidOperation, ValueError):
            pass
    return str(value)


def changes(entry):
    result = []
    model = entry.content_type.model_class() if entry.content_type_id else None
    for field, values in (entry.diff or {}).items():
        if (
            field in {"id", "updated_at"}
            or not isinstance(values, (list, tuple))
            or len(values) != 2
        ):
            continue
        label = field.replace("_", " ").capitalize()
        if model:
            with contextlib.suppress(FieldDoesNotExist):
                label = str(model._meta.get_field(field).verbose_name).capitalize()
        before, after = _value(values[0], field), _value(values[1], field)
        # e.g. "" → None both read «Vacío»: nothing the owner could see changed.
        if before == after and before != "(oculto por seguridad)":
            continue
        result.append({"label": label, "before": before, "after": after})
    return result
