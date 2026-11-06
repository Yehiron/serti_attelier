"""Validación compartida, sin exponer valores de secretos."""

from typing import Any
from urllib.parse import urlsplit

KEY_PREFIXES = {
    "WOMPI_PUBLIC_KEY": ("pub_test_", "pub_prod_"),
    "WOMPI_PRIVATE_KEY": ("prv_test_", "prv_prod_"),
    "WOMPI_INTEGRITY_SECRET": ("test_integrity_", "prod_integrity_"),
    "WOMPI_EVENTS_SECRET": ("test_events_", "prod_events_"),
}
URLS = ("https://sandbox.wompi.co/v1", "https://production.wompi.co/v1")


def fake_api_enabled(config: Any) -> bool:
    get = config.get if isinstance(config, dict) else lambda name: getattr(config, name, "")
    try:
        url = urlsplit(get("WOMPI_API_URL") or "")
        port = url.port
    except (ValueError, TypeError):
        return False
    return bool(
        get("DEBUG")
        and get("WOMPI_ALLOW_FAKE_API")
        and url.scheme == "http"
        and url.hostname == "wompi-fake"
        and port in (None, 8080)
        and url.path == "/v1"
        and not url.username
        and not url.password
        and not url.query
        and not url.fragment
    )


def configuration_errors(config: Any) -> list[str]:
    get = config.get if isinstance(config, dict) else lambda name: getattr(config, name, "")
    errors = []
    url = get("WOMPI_API_URL")
    fake = fake_api_enabled(config)
    if url not in URLS and not fake:
        errors.append("WOMPI_API_URL debe ser una URL oficial de Wompi.")
    for name, prefixes in KEY_PREFIXES.items():
        value = get(name)
        if not value:
            errors.append(f"Falta {name} para habilitar Wompi.")
        elif not isinstance(value, str) or not value.startswith(prefixes) or value in prefixes:
            errors.append(f"{name} tiene un prefijo inválido.")
        elif fake and not value.startswith(prefixes[0] + "e2e"):
            errors.append(f"{name} requiere una llave ficticia e2e.")
        elif url in URLS and not value.startswith(prefixes[URLS.index(url)]):
            errors.append(f"{name} no coincide con el entorno de WOMPI_API_URL.")
    return errors
