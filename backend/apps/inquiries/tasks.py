import logging
import unicodedata
from urllib.parse import urlencode, urlsplit

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse

from apps.core.selectors import get_solo

from .models import ContactInquiry

logger = logging.getLogger(__name__)


def subject_name(name):
    clean = "".join(" " if unicodedata.category(char).startswith("C") else char
                    for char in name if char not in "<>")
    return " ".join(clean.split())[:80].rstrip()


@shared_task(autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def notify_atelier(pk):
    inquiry = ContactInquiry.objects.get(pk=pk)
    config = get_solo()
    url = settings.PUBLIC_SITE_URL.rstrip("/") + reverse(
        "admin:inquiries_contactinquiry_change", args=[pk]
    )
    context = {"inquiry": inquiry, "url": url}
    if config.support_email:
        email = EmailMultiAlternatives(
            f"Nuevo mensaje · {inquiry.get_topic_display()} · {subject_name(inquiry.name)}",
            render_to_string("inquiries/atelier.txt", context),
            settings.DEFAULT_FROM_EMAIL,
            [config.support_email],
            reply_to=[inquiry.email],
        )
        email.attach_alternative(render_to_string("inquiries/atelier.html", context), "text/html")
        email.send()
    else:
        logger.warning("Correo de soporte sin configurar para mensajes de contacto")


# Tareas separadas: un reintento del acuse al cliente no reenvía el aviso al atelier.
@shared_task(autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def send_acknowledgement(pk):
    inquiry = ContactInquiry.objects.get(pk=pk)
    config = get_solo()
    locale = inquiry.locale
    site_url = settings.PUBLIC_SITE_URL.rstrip("/")
    parsed = urlsplit(site_url)
    text = ("Hola SERTI, les escribí por la página." if locale == "es"
            else "Hello SERTI, I wrote to you through the website.")
    context = {
        "inquiry": inquiry,
        "locale": locale,
        "title": "Recibimos tu carta" if locale == "es" else "We received your letter",
        "channel": ("correo" if locale == "es" else "email")
        if inquiry.preferred_channel == "email" else "WhatsApp",
        "whatsapp_url": f"https://wa.me/{config.whatsapp_number}?{urlencode({'text': text})}"
        if config.whatsapp_number else "",
        "support_email": config.support_email,
        "monogram_url": f"{site_url}/brand/monogram-email.png"
        if parsed.scheme in {"http", "https"} and parsed.netloc else "",
    }
    subject = "Recibimos tu carta" if locale == "es" else "We received your letter"
    email = EmailMultiAlternatives(
        subject,
        render_to_string("inquiries/customer.txt", context),
        settings.DEFAULT_FROM_EMAIL,
        [inquiry.email],
    )
    email.attach_alternative(render_to_string("inquiries/customer.html", context), "text/html")
    email.send()
