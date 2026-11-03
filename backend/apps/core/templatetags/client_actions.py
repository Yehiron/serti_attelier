from __future__ import annotations

from typing import Any

from django import template

from apps.catalog.models import Piece

register = template.Library()


@register.simple_tag
def client_row_actions(actions: list[dict[str, Any]], instance: Any) -> list[dict[str, Any]]:
    if isinstance(instance, Piece) and instance.status not in ("draft", "hidden"):
        return [a for a in actions if a["raw_path"] != "admin:catalog_piece_detail_publish"]
    return actions
