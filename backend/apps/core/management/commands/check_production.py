"""Explicit launch gate; importing production settings never runs dependency checks."""

from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.accounts.roles import PROPIETARIO
from apps.catalog.models import Piece
from apps.cms.models import HomePublication, PageRevision
from apps.cms.selectors import published_pages
from apps.core import health
from apps.core.models import SiteSettings
from apps.notifications.email_checks import sender_errors
from apps.payments.configuration import configuration_errors


def wompi_coherent() -> bool:
    return not configuration_errors(settings)


class Command(BaseCommand):
    help = "Comprueba si el sitio está listo para producción."

    def handle(self, *args: Any, **options: Any) -> None:
        failures = 0

        def report(label: str, ok: bool, *, warning: bool = False) -> None:
            nonlocal failures
            symbol = "✅" if ok else ("⚠️" if warning else "❌")
            self.stdout.write(f"{symbol} {label}")
            if not ok and not warning:
                failures += 1

        secret = settings.SECRET_KEY
        report("DEBUG desactivado", not settings.DEBUG)
        report(
            "Clave secreta segura (mínimo 50 caracteres)",
            len(secret) >= 50
            and not any(
                text in secret.lower()
                for text in ("change-me", "changeme", "django-insecure", "placeholder", "dev-only")
            )
            and len(set(secret)) >= 10,
        )
        report(
            "Hosts explícitos", bool(settings.ALLOWED_HOSTS) and "*" not in settings.ALLOWED_HOSTS
        )
        public = urlsplit(settings.PUBLIC_SITE_URL)
        report("URL pública HTTPS", public.scheme == "https" and bool(public.hostname))
        report("Pepper de cupones (mínimo 32 caracteres)", len(settings.COUPON_EMAIL_PEPPER) >= 32)
        report("Token interno (mínimo 32 caracteres)", len(settings.INTERNAL_API_TOKEN) >= 32)
        database_ok = health.check_database()
        report("Base de datos accesible", database_ok)
        report("Redis accesible", health.check_redis())
        migrations_ok = health.check_migrations(cached=False)
        report("Migraciones aplicadas", migrations_ok)
        report("Llaves Wompi completas y coherentes con su URL", wompi_coherent())
        report("Correo SMTP configurado", bool(settings.EMAIL_HOST), warning=True)
        for problem in sender_errors(settings):
            report(f"Correo: {problem}", False)
        report("Correo de pedidos configurado", bool(settings.SERTI_ORDERS_EMAIL), warning=True)
        report("WhatsApp con proveedor real", settings.WHATSAPP_PROVIDER != "log", warning=True)
        report("Sentry habilitado", bool(getattr(settings, "SENTRY_DSN", "")), warning=True)
        report(
            "Wompi fuera de sandbox",
            settings.WOMPI_PUBLIC_KEY.startswith("pub_prod_"),
            warning=True,
        )
        if database_ok and migrations_ok:
            try:
                owners = User.objects.filter(is_active=True, groups__name=PROPIETARIO)
                report(
                    "Propietario activo con TOTP confirmado",
                    TOTPDevice.objects.filter(user__in=owners, confirmed=True).exists(),
                )
                pages = published_pages()
                kinds = {page.kind for page, revision in pages}
                for kind in ("terms", "privacy"):
                    report(f"Página legal publicada: {kind}", kind in kinds)
                legal_revisions = PageRevision.objects.filter(
                    page__kind__in=("terms", "privacy", "returns", "shipping", "cookies")
                )
                latest_ids = [
                    revision.pk
                    for page, revision in pages
                    if page.kind in ("terms", "privacy", "returns", "shipping", "cookies")
                ]
                report(
                    "Textos legales definitivos",
                    not any(
                        "texto provisional" in str(revision.snapshot).lower()
                        for revision in legal_revisions.filter(pk__in=latest_ids)
                    ),
                    warning=True,
                )
                report(
                    "WhatsApp del sitio configurado",
                    SiteSettings.objects.exclude(whatsapp_number="").exists(),
                    warning=True,
                )
                report("Inicio publicado", HomePublication.objects.exists(), warning=True)
                report(
                    "Sin piezas de demostración",
                    not Piece.objects.filter(
                        Q(sku__startswith="DEMO-") | Q(sku__startswith="E2E-")
                    ).exists(),
                    warning=True,
                )
            except Exception:
                report("Comprobaciones de contenido y propietario disponibles", False)
        else:
            report("Comprobaciones de contenido y propietario requieren base migrada", False)
        if failures:
            raise CommandError(
                f"Producción no preparada: {failures} comprobaciones bloqueantes fallaron."
            )
