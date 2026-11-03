"""Client navigation and admin-only presentation policies."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.contrib import admin
from django.http import HttpRequest
from django.templatetags.static import static
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

TECHNICAL_MODELS = {
    "audit.auditlog",
    "axes.accessattempt",
    "axes.accessfailurelog",
    "axes.accesslog",
    "payments.paymentattempt",
    "payments.paymentevent",
    "notifications.notificationdelivery",
    "cms.homepublication",
    "cms.pagerevision",
    "inventory.piecestatuschange",
    "inventory.piecereservation",
    "catalog.pieceimage",
    "otp_totp.totpdevice",
    "auth.group",
    "core.department",
    "core.municipality",
}


def permission(name: str) -> Callable[[HttpRequest], bool]:
    return lambda request: request.user.has_perm(name)


def superuser(request: HttpRequest) -> bool:
    return request.user.is_active and request.user.is_superuser


def technical_permission(model: str) -> Callable[[HttpRequest], bool]:
    app, name = model.split(".")
    return lambda request: superuser(request) and request.user.has_perm(f"{app}.view_{name}")


def item(title: str, icon: str, model: str) -> dict[str, Any]:
    app, name = model.split(".")
    return {
        "title": _(title),
        "icon": icon,
        "link": reverse_lazy(f"admin:{app}_{name}_changelist"),
        "permission": permission(f"{app}.view_{name}"),
    }


NAVIGATION: list[dict[str, Any]] = [
    {
        "items": [
            {
                "title": _("Inicio"),
                "icon": "home",
                "link": reverse_lazy("admin:index"),
                "permission": lambda request: request.user.is_active and request.user.is_staff,
            }
        ]
    },
    {"title": _("Pedidos"), "items": [item("Pedidos", "shopping_bag", "orders.order")]},
    {
        "title": _("Catálogo"),
        "items": [
            item(title, icon, f"catalog.{model}")
            for title, icon, model in [
                ("Piezas", "diamond", "piece"),
                ("Categorías", "category", "category"),
                ("Piedras", "deployed_code", "stone"),
                ("Colecciones", "collections", "collection"),
                ("Materiales", "texture", "material"),
            ]
        ],
    },
    {
        "title": _("Página web"),
        "items": [
            item("Portada", "web", "cms.homesection"),
            item("Páginas", "article", "cms.page"),
            item("Servicios de personalización", "design_services", "cms.personalizationservice"),
        ],
    },
    {"title": _("Promociones"), "items": [item("Cupones", "sell", "promotions.coupon")]},
    {
        "title": _("Ajustes"),
        "items": [
            item("Datos del sitio", "settings", "core.sitesettings"),
            item("Equipo", "group", "accounts.user"),
        ],
    },
    {
        "title": _("Herramientas técnicas"),
        "collapsible": True,
        "items": [
            {**item(title, "build", model), "permission": technical_permission(model)}
            for title, model in [
                ("Auditoría", "audit.auditlog"),
                ("Intentos de acceso", "axes.accessattempt"),
                ("Fallos de acceso", "axes.accessfailurelog"),
                ("Accesos", "axes.accesslog"),
                ("Intentos de pago", "payments.paymentattempt"),
                ("Eventos de pago", "payments.paymentevent"),
                ("Entregas de notificaciones", "notifications.notificationdelivery"),
                ("Publicaciones del inicio", "cms.homepublication"),
                ("Revisiones de páginas", "cms.pagerevision"),
                ("Cambios de estado", "inventory.piecestatuschange"),
                ("Reservas de piezas", "inventory.piecereservation"),
                ("Imágenes de piezas", "catalog.pieceimage"),
                ("Dispositivos de verificación (2FA)", "otp_totp.totpdevice"),
                ("Grupos", "auth.group"),
                ("Departamentos", "core.department"),
                ("Municipios", "core.municipality"),
            ]
        ],
    },
]


def navigation(request: HttpRequest) -> list[dict[str, Any]]:
    return [
        group
        for group in NAVIGATION
        if any(entry["permission"](request) for entry in group["items"])
    ]


def logo_light(request: HttpRequest) -> str:
    return static("core/brand/wordmark-wine.webp")


def logo_dark(request: HttpRequest) -> str:
    return static("core/brand/wordmark-gold.webp")


def icon(request: HttpRequest) -> str:
    return static("core/brand/icon-192.png")


def favicon(request: HttpRequest) -> str:
    return static("core/brand/favicon.svg")


class TechnicalAdminMixin:
    """Restrict admin screens without changing domain or role permissions."""

    def has_module_permission(self, request: HttpRequest) -> bool:
        return superuser(request)

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return superuser(request)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return superuser(request) and bool(super().has_add_permission(request))  # type: ignore[misc]

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return superuser(request) and bool(super().has_change_permission(request, obj))  # type: ignore[misc]

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return superuser(request) and bool(super().has_delete_permission(request, obj))  # type: ignore[misc]


def configure_technical_admins() -> None:
    # Autodiscovery is complete here; retain each third-party admin's implementation.
    for model, model_admin in list(admin.site._registry.items()):
        if model._meta.label_lower in TECHNICAL_MODELS and not isinstance(
            model_admin, TechnicalAdminMixin
        ):
            restricted = type(
                f"ClientRestricted{type(model_admin).__name__}",
                (TechnicalAdminMixin, type(model_admin)),
                {},
            )
            admin.site.unregister(model)
            admin.site.register(model, restricted)
