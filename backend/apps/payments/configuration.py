"""Validación compartida, sin exponer valores de secretos."""

from typing import Any

KEY_PREFIXES = {
    "WOMPI_PUBLIC_KEY": ("pub_test_", "pub_prod_"),
    "WOMPI_PRIVATE_KEY": ("prv_test_", "prv_prod_"),
    "WOMPI_INTEGRITY_SECRET": ("test_integrity_", "prod_integrity_"),
    "WOMPI_EVENTS_SECRET": ("test_events_", "prod_events_"),
}
URLS = ("https://sandbox.wompi.co/v1", "https://production.wompi.co/v1")


def configuration_errors(config: Any) -> list[str]:
    get = config.get if isinstance(config, dict) else lambda name: getattr(config, name, "")
    errors = []
    url = get("WOMPI_API_URL")
    if url not in URLS:
        errors.append("WOMPI_API_URL debe ser una URL oficial de Wompi.")
    for name, prefixes in KEY_PREFIXES.items():
        value = get(name)
        if not value:
            errors.append(f"Falta {name} para habilitar Wompi.")
        elif not isinstance(value, str) or not value.startswith(prefixes) or value in prefixes:
            errors.append(f"{name} tiene un prefijo inválido.")
        elif url in URLS and not value.startswith(prefixes[URLS.index(url)]):
            errors.append(f"{name} no coincide con el entorno de WOMPI_API_URL.")
    return errors
