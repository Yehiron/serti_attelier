from typing import Any
from urllib.parse import quote

ROUTES = {
    "cart": ("carrito", "cart"),
    "checkout": ("checkout", "checkout"),
    "order": ("pedido", "order"),
    "home": ("", ""),
    "catalog": ("joyeria", "jewelry"),
    "category": ("joyeria", "jewelry"),
    "stone": ("piedras", "stones"),
    "collection": ("colecciones", "collections"),
    "piece": ("piezas", "pieces"),
    "personalize": ("personaliza", "customize"),
    "story": ("historia", "story"),
    "contact": ("contacto", "contact"),
    "wishlist": ("deseos", "wishlist"),
    "search": ("buscar", "search"),
    "page": ("legal", "legal"),
}


def href(route_key: str, locale: str, obj: Any = None) -> str:
    if locale not in {"es", "en"}:
        raise ValueError("Unsupported locale")
    segment = ROUTES[route_key][locale == "en"]
    path = f"/{locale}" + (f"/{segment}" if segment else "")
    if route_key in {"category", "stone", "collection", "piece", "page"}:
        slug = getattr(obj, f"slug_{locale}", "") or getattr(obj, "slug_es", "")
        if not slug:
            raise ValueError("A localized slug is required")
        path += f"/{quote(slug, safe='')}"
    if route_key == "order":
        path += f"/{quote(str(getattr(obj, 'public_token', obj)), safe='')}"
    return path
