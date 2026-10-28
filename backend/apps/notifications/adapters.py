"""Channel adapters. Register these exact Spanish body texts with Meta as utility.

WHATSAPP_TEMPLATE_NEW_ORDER (suggested name: nuevo_pedido):
Nuevo pedido {{1}}. Cliente: {{2}}. Piezas: {{3}}. Total: {{4}}.
Destino: {{5}}. Certificado: {{6}}. Revisar pedido: {{7}}

WHATSAPP_TEMPLATE_NEEDS_ATTENTION (suggested name: pedido_requiere_atencion):
URGENTE: el pedido {{1}} requiere atención. Cliente: {{2}}. Piezas: {{3}}.
Total: {{4}}. Destino: {{5}}. Certificado: {{6}}. Revisar pedido: {{7}}.
Motivo: {{8}}. Requiere reembolso o contacto con el cliente.

Cloud success means accepted by Meta, not delivered to the handset.
"""

from __future__ import annotations

import json
import logging
import re
from email.utils import make_msgid
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


class ChannelFailure(Exception):
    """Fixed error codes only; never include provider responses or exception strings."""


class ChannelSkipped(Exception):
    """Fixed configuration reasons only."""


def send_email(recipient: str, subject: str, text: str, html: str, reply_to: str) -> str:
    message_id = make_msgid(domain=urlsplit(settings.PUBLIC_SITE_URL).hostname or "localhost")
    message = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
        reply_to=[reply_to] if reply_to else [],
        headers={"Message-ID": message_id},
    )
    message.attach_alternative(html, "text/html")
    try:
        if message.send() != 1:
            raise ChannelFailure("email_not_accepted")
    except ChannelFailure:
        raise
    except Exception as exc:
        # Only the exception type name: never the message, which may hold addresses.
        raise ChannelFailure(f"email_send_failed:{type(exc).__name__}") from None
    # SMTP exposes no provider ID; retain the RFC Message-ID for support correlation.
    return message_id


def whatsapp_template(event: str) -> str:
    return str(
        settings.WHATSAPP_TEMPLATE_NEEDS_ATTENTION
        if event == "needs_attention"
        else settings.WHATSAPP_TEMPLATE_NEW_ORDER
    )


def whatsapp_unavailable(event: str) -> str:
    if settings.WHATSAPP_PROVIDER == "log":
        return ""
    if settings.WHATSAPP_PROVIDER != "cloud":
        return "whatsapp_provider_unconfigured"
    if not all(
        (
            settings.WHATSAPP_ACCESS_TOKEN,
            settings.WHATSAPP_PHONE_NUMBER_ID,
            settings.WHATSAPP_ORDERS_RECIPIENT,
            whatsapp_template(event),
        )
    ):
        return "whatsapp_unconfigured"
    if not (
        re.fullmatch(r"[1-9][0-9]{1,14}", settings.WHATSAPP_ORDERS_RECIPIENT)
        and re.fullmatch(r"[0-9]+", settings.WHATSAPP_PHONE_NUMBER_ID)
        and re.fullmatch(r"v[0-9]+\.[0-9]+", settings.WHATSAPP_API_VERSION)
    ):
        return "whatsapp_configuration_invalid"
    return ""


def send_whatsapp(event: str, parameters: list[str], delivery_id: int) -> str:
    reason = whatsapp_unavailable(event)
    if reason:
        raise ChannelSkipped(reason)
    if settings.WHATSAPP_PROVIDER == "log":
        logger.info("WhatsApp log delivery=%s event=%s", delivery_id, event)
        return f"log-{delivery_id}"
    body = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": settings.WHATSAPP_ORDERS_RECIPIENT,
        "type": "template",
        "template": {
            "name": whatsapp_template(event),
            "language": {"code": settings.WHATSAPP_TEMPLATE_LANG},
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": p} for p in parameters]}
            ],
        },
    }
    request = Request(
        f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/"
        f"{settings.WHATSAPP_PHONE_NUMBER_ID}/messages",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310  # Fixed HTTPS origin.
            if response.status != 200:
                raise ValueError
            result = json.loads(response.read(65536))
        message_id = result["messages"][0]["id"]
        if not isinstance(message_id, str) or not re.fullmatch(
            r"wamid[.A-Za-z0-9_+=/-]{1,194}", message_id
        ):
            raise ValueError
        return message_id
    except TimeoutError:
        raise ChannelFailure("whatsapp_timeout") from None
    except ChannelFailure:
        raise
    except Exception as exc:
        raise ChannelFailure(f"whatsapp_send_failed:{type(exc).__name__}") from None
