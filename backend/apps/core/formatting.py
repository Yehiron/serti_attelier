"""Customer-facing formatting shared by the API texts and (Phase 7) emails.

Kept dependency-free: COP amounts and Colombia-time dates in Spanish or English,
matching what the frontend shows with Intl (es-CO / en-US).
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")

_MONTHS = {
    "es": [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ],
    "en": [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ],
}  # fmt: skip


def format_cop(cents: int, locale: str) -> str:
    """'$ 4.000.000' (es) or 'COP 4,000,000' (en); centavos only when present."""
    pesos, rest = divmod(abs(cents), 100)
    sign = "-" if cents < 0 else ""
    if locale == "en":
        decimals = f".{rest:02d}" if rest else ""
        return f"{sign}COP {pesos:,}{decimals}"
    grouped = f"{pesos:,}".replace(",", ".")
    decimals = f",{rest:02d}" if rest else ""
    return f"{sign}$ {grouped}{decimals}"


def format_admin_cop(cents: int) -> str:
    """Compact Spanish COP notation for the client dashboard."""
    return format_cop(cents, "es").replace("$ ", "$")


def format_bogota_datetime(value: datetime, locale: str) -> str:
    """'25 de octubre de 2026, 2:23 p. m. (hora de Colombia)' or the English equivalent."""
    local = value.astimezone(BOGOTA)
    hour = local.hour % 12 or 12
    month = _MONTHS["en" if locale == "en" else "es"][local.month - 1]
    if locale == "en":
        meridiem = "AM" if local.hour < 12 else "PM"
        time = f"{hour}:{local.minute:02d} {meridiem}"
        return f"{month} {local.day}, {local.year}, {time} (Colombia time)"
    meridiem = "a. m." if local.hour < 12 else "p. m."
    return (
        f"{local.day} de {month} de {local.year}, {hour}:{local.minute:02d} {meridiem} "
        "(hora de Colombia)"
    )


_LOWERCASE_PLACE_WORDS = {"de", "del", "la", "las", "los", "el", "y", "e", "en"}


def place_name(raw: str) -> str:
    """DANE names come upper-case ('SAN ANDRÉS DE TUMACO'); show them as 'San Andrés de Tumaco'.

    Connectors stay lower-case except at the start, and dotted abbreviations ('D.C.') are kept.
    """
    words = raw.strip().split()
    result = []
    for index, word in enumerate(words):
        lower = word.lower()
        if "." in word:
            result.append(word.upper())
        elif index > 0 and lower.rstrip(",") in _LOWERCASE_PLACE_WORDS:
            result.append(lower)
        else:
            result.append("-".join(part.capitalize() for part in lower.split("-")))
    return " ".join(result)


def format_bogota_date(value: datetime, locale: str) -> str:
    """'25 de octubre de 2026' or 'October 25, 2026' (Colombia calendar day)."""
    local = value.astimezone(BOGOTA)
    month = _MONTHS["en" if locale == "en" else "es"][local.month - 1]
    if locale == "en":
        return f"{month} {local.day}, {local.year}"
    return f"{local.day} de {month} de {local.year}"
