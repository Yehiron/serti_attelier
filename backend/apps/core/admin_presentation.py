"""Presentation helpers; persistence remains in each model admin's services."""

from __future__ import annotations

from typing import Any, cast

from django.contrib import admin
from django.http import HttpRequest
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.decorators import display
from unfold.utils import display_for_label

HELP = {
    "name": _("Nombre que verá el cliente en la página web."),
    "title": _("Título que se mostrará en la página web."),
    "short_description": _("Una frase breve para presentar la pieza en el catálogo."),
    "long_description": _("Cuenta los detalles, el tamaño y el acabado de la pieza."),
    "care": _("Explica cómo limpiar y conservar la pieza."),
    "is_primary": _("Usa esta foto como imagen principal del catálogo."),
    "is_hover": _("Muestra esta foto cuando el cliente pase el cursor por la pieza."),
    "category": _("Elige la categoría donde aparecerá la pieza."),
    "is_active": _("Activa esta opción para que esté disponible en la página web."),
    "subtitle": _("Texto breve que acompaña al título."),
    "body": _("Contenido que se mostrará al visitar esta sección."),
    "cta_label": _("Texto del botón que abrirá el enlace."),
    "cta_kind": _("Elige a dónde llevará el botón de esta sección."),
    "starts_at": _("Fecha a partir de la cual se puede usar el cupón. Opcional."),
    "ends_at": _("Última fecha para usar el cupón. Opcional."),
    "max_uses": _("Número máximo de usos del cupón. Déjalo vacío si no hay límite."),
    "max_uses_per_email": _("Usos permitidos por cliente. Déjalo vacío si no hay límite."),
    "manual_payment_instructions": _(
        "Instrucciones que recibirá el cliente. Conserva los textos entre llaves."
    ),
    "certificate_price_cents": _(
        "Precio en pesos que se cobra si el cliente solicita un certificado."
    ),
    "stones": _("Pasa a la derecha las piedras de la pieza."),
    "materials": _("Pasa a la derecha los materiales de la pieza."),
    "related": _("Piezas que se sugieren al final de esta pieza en la página web."),
    "description": _("Describe la pieza o el contenido con palabras sencillas."),
    "original": _("Sube una foto nítida de la pieza."),
    "image": _("Selecciona la imagen que se mostrará en esta sección."),
    "cover_image": _("Selecciona una imagen para la portada del catálogo."),
    "alt": _("Describe la imagen para las personas que no pueden verla."),
    "image_alt": _("Describe la imagen para las personas que no pueden verla."),
    "price_cents": _("Escribe el precio en pesos colombianos, sin separadores de miles."),
    "sale_price_cents": _("Precio de oferta en pesos. Déjalo vacío si no hay oferta."),
    "position": _("Arrastra las filas para cambiar el orden."),
    "is_visible": _("Activa esta opción para incluir la sección al publicar el inicio."),
    "whatsapp_number": _("Escribe el indicativo y el número, por ejemplo 573001234567."),
    "support_email": _("Correo donde los clientes pueden pedir ayuda."),
    "code": _("Código que escribirá el cliente para usar el cupón."),
    "amount": _("Escribe el porcentaje o el valor en pesos, según el tipo de cupón."),
    "min_subtotal_cents": _(
        "Compra mínima en pesos para usar este cupón. Cero significa sin mínimo."
    ),
}


def thumbnail_url(image: Any) -> str:
    """Smallest WebP rendition for admin thumbnails; the original only while it is processing."""
    from django.core.files.storage import default_storage

    paths = (getattr(image, "renditions", None) or {}).get("webp", {})
    return default_storage.url(paths[min(paths, key=int)]) if paths else str(image.original.url)


MULTI_SELECT = {"stones", "materials", "related"}


class ClientPresentationMixin:
    def get_form(
        self, request: HttpRequest, obj: Any = None, change: bool = False, **kwargs: Any
    ) -> Any:
        form = super().get_form(request, obj, change=change, **kwargs)  # type: ignore[misc]
        for name, field in form.base_fields.items():
            if hasattr(field, "empty_label"):
                field.empty_label = _("Selecciona una opción")
            field.widget.attrs["data-placeholder"] = _("Selecciona una opción")
            base = name.removesuffix("_es").removesuffix("_en")
            if base in HELP and not field.help_text:
                field.help_text = HELP[base]
            if base in MULTI_SELECT:
                # Replaces Django's "hold Control/Command" hint, wrong for the two-list widget.
                field.help_text = HELP[base]
            if base.startswith("whatsapp_") and base != "whatsapp_number":
                field.help_text = _(
                    "Mensaje para WhatsApp. Conserva los textos entre llaves; "
                    "se completan automáticamente."
                )
            if base == "slug":
                field.label = _("Dirección en la web")
        return form

    def get_fieldsets(self, request: HttpRequest, obj: Any = None) -> Any:
        fieldsets = super().get_fieldsets(request, obj)  # type: ignore[misc]
        if len(fieldsets) != 1 or fieldsets[0][0] is not None:
            return fieldsets
        fields = list(fieldsets[0][1]["fields"])
        advanced = [
            f
            for f in fields
            if isinstance(f, str)
            and (
                f.startswith("slug")
                or f
                in {
                    "position",
                    "sku",
                    "piece_number",
                    "attributes",
                    "created_at",
                    "updated_at",
                    "published_at",
                    "sold_at",
                    "version",
                    "online_reservation_minutes",
                    "manual_reservation_hours",
                }
            )
        ]
        if not advanced:
            return fieldsets
        return [
            (None, {"fields": [f for f in fields if f not in advanced]}),
            (_("Avanzado"), {"classes": ["collapse"], "fields": advanced}),
        ]

    @admin.display(description=_("Vista previa"))
    def image_preview(self, obj: Any) -> str:
        image = (
            getattr(obj, "image", None)
            or getattr(obj, "cover_image", None)
            or getattr(obj, "original", None)
        )
        return (
            format_html('<img src="{}" style="max-width:240px;max-height:160px" alt="">', image.url)
            if image
            else "—"
        )

    @display(description=_("Estado"), label=True)  # type: ignore[untyped-decorator]
    def image_status(self, obj: Any) -> str:
        status = getattr(obj, "processing_status", "ready")
        if status == "failed":
            # Decoder/worker errors can include implementation details; give an actionable message.
            text = _("Error: vuelve a subir la imagen o contacta con soporte.")
        elif status != "ready":
            text = _("Procesando…")
        elif any(
            getattr(obj, f, None) for f in ("image", "image_mobile", "cover_image", "original")
        ):
            text = _("Lista")
        else:
            return "—"
        return cast(
            str,
            display_for_label(
                (status, str(text)),
                "—",
                {
                    "ready": "success",
                    "failed": "danger",
                    "pending": "warning",
                    "processing": "warning",
                },
            ),
        )
