"""Send one sample email through the configured provider (fictitious data only).

Use it after configuring SMTP and DNS, for example with the address mail-tester.com shows,
then check that SPF, DKIM and DMARC pass.
"""

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.core.validators import validate_email

from apps.core.models import SiteSettings
from apps.notifications.adapters import ChannelFailure, send_email
from apps.notifications.email_checks import sender_errors

TEXT = """Hola.

Este es un correo de prueba de SERTI para comprobar que los avisos de pedidos llegan a la
bandeja de entrada. No contiene datos de ningún pedido real.

Pedido de ejemplo SRT-000000 · Pago aprobado · Total $ 150.000

SERTI · Colombia
"""

HTML = """<!doctype html><html lang="es"><body style="margin:0;padding:24px;background:#ead9cb;
color:#330414;font-family:Helvetica,Arial,sans-serif;"><table role="presentation" width="100%"
cellspacing="0" cellpadding="0" border="0"
style="max-width:560px;margin:0 auto;background:#f6efe8;">
<tr><td style="padding:32px;"><p style="font-size:11px;letter-spacing:3px;color:#651c32;">SERTI ·
PRUEBA</p><h1 style="font-family:Georgia,serif;font-weight:400;color:#651c32;">Correo de prueba</h1>
<p style="line-height:1.7;">Este es un correo de prueba de SERTI para comprobar que los avisos de
pedidos llegan a la bandeja de entrada. No contiene datos de ningún pedido real.</p>
<p style="line-height:1.7;">Pedido de ejemplo SRT-000000 · Pago aprobado · Total $ 150.000</p>
<p style="font-size:11px;letter-spacing:2px;color:#58513d;">SERTI · COLOMBIA</p></td></tr></table>
</body></html>"""


class Command(BaseCommand):
    help = "Envía un correo de prueba con datos ficticios por el proveedor configurado."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("recipient", help="Dirección de destino, p. ej. la de mail-tester.com")

    def handle(self, *args: Any, recipient: str, **options: Any) -> None:
        try:
            validate_email(recipient)
        except ValidationError as exc:
            raise CommandError("Dirección de destino inválida.") from exc
        for problem in sender_errors(settings):
            self.stdout.write(self.style.WARNING(f"⚠️  {problem}"))
        site = SiteSettings.objects.first()
        reply_to = getattr(site, "support_email", "") or ""
        try:
            message_id = send_email(recipient, "SERTI · Correo de prueba", TEXT, HTML, reply_to)
        except ChannelFailure as exc:
            raise CommandError(f"El proveedor no aceptó el correo ({exc}).") from None
        self.stdout.write(self.style.SUCCESS(f"Enviado desde {settings.DEFAULT_FROM_EMAIL}."))
        self.stdout.write(f"Message-ID: {message_id}")
