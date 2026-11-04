from __future__ import annotations

import re
from typing import Any

from django import template
from django.utils.html import escape, format_html
from django.utils.safestring import SafeString, mark_safe

from apps.catalog.models import Piece

register = template.Library()


@register.simple_tag
def client_row_actions(actions: list[dict[str, Any]], instance: Any) -> list[dict[str, Any]]:
    if isinstance(instance, Piece) and instance.status not in ("draft", "hidden"):
        return [a for a in actions if a["raw_path"] != "admin:catalog_piece_detail_publish"]
    return actions


@register.filter
def title_lines(text: str) -> SafeString:
    """Mirror the site's title rule (frontend/lib/title.ts): " / " breaks lines, last one italic."""
    lines = [line.strip() for line in re.split(r"\s+/\s+|\n", text or "") if line.strip()]
    parts = [
        format_html("<em>{}</em>", line) if len(lines) > 1 and i == len(lines) - 1 else escape(line)
        for i, line in enumerate(lines)
    ]
    return mark_safe("<br>".join(parts))  # noqa: S308 - every part is escaped above.
