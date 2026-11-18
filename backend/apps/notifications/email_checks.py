"""Sender checks for deliverability: mail must come from the shop's own domain over TLS."""

from email.utils import parseaddr
from typing import Any
from urllib.parse import urlsplit

PLACEHOLDER_DOMAINS = ("localhost", "example.com", "example.org", "serti.localhost", ".test")


def sender_domain(config: Any) -> str:
    return parseaddr(config.DEFAULT_FROM_EMAIL)[1].rpartition("@")[2].lower()


def site_domain(config: Any) -> str:
    host = (urlsplit(config.PUBLIC_SITE_URL).hostname or "").lower()
    return host.removeprefix("www.")


def sender_errors(config: Any) -> list[str]:
    """Problems that send order mail to spam or leave it unsent. Empty when SMTP is unset."""
    if not config.EMAIL_HOST:
        return []
    errors = []
    domain, site = sender_domain(config), site_domain(config)
    placeholder = any(domain == p.lstrip(".") or domain.endswith(p) for p in PLACEHOLDER_DOMAINS)
    if not domain or placeholder:
        errors.append("El remitente (DEFAULT_FROM_EMAIL) usa un dominio de ejemplo.")
    elif site and domain != site and not domain.endswith("." + site):
        errors.append(
            "El remitente (DEFAULT_FROM_EMAIL) debe usar el dominio de la tienda para que "
            "SPF/DKIM/DMARC lo autentiquen."
        )
    if not (config.EMAIL_USE_TLS or config.EMAIL_USE_SSL):
        errors.append("La conexión SMTP debe usar TLS (EMAIL_USE_TLS=true, puerto 587).")
    if not config.EMAIL_HOST_USER or not config.EMAIL_HOST_PASSWORD:
        errors.append("Faltan las credenciales SMTP (EMAIL_HOST_USER / EMAIL_HOST_PASSWORD).")
    return errors
