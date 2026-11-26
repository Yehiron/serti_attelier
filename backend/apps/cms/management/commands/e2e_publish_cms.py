"""Publish every CMS document of a fresh development database (DEBUG only).

A new install starts with drafts only: no published home, legal pages or menus, so
checkout and contact stay disabled. Browser tests (and a new developer) need the same
starting point as a working shop. Publishing goes through the normal services. A blank
WhatsApp number gets an obviously fake one so the contact links render.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.accounts.roles import PROPIETARIO
from apps.accounts.services import sync_roles
from apps.cms import brand, services
from apps.cms.documents import document_key, get_document
from apps.cms.menus import MENU_KEYS, publish_menu
from apps.cms.models import Page
from apps.cms.publishing import pending_changes
from apps.core.selectors import get_solo

PUBLISHER = "e2e-cms-publisher"
FAKE_WHATSAPP = "570000000000"


class Command(BaseCommand):
    help = "Publica inicio, páginas, menús y marca de una base de desarrollo (solo DEBUG)."

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError("e2e_publish_cms solo funciona con DEBUG activo.")
        sync_roles()
        user, _ = User.objects.get_or_create(
            username=PUBLISHER,
            defaults={"email": f"{PUBLISHER}@e2e.invalid", "is_staff": True},
        )
        user.groups.add(Group.objects.get(name=PROPIETARIO))

        def version(key: str) -> int:
            return int(get_document(key).draft_version)

        def needed(key: str) -> bool:
            return bool(pending_changes(key)["count"])

        with transaction.atomic():
            site = get_solo()
            if not site.whatsapp_number:
                site.whatsapp_number = FAKE_WHATSAPP
                site.save(update_fields=["whatsapp_number"])
                self.stdout.write("whatsapp de prueba")
            for page in Page.objects.order_by("pk"):
                key = document_key(page)
                if page.status != "published" or needed(key):
                    services.publish_page(page, user, note="E2E", expected_version=version(key))
                    self.stdout.write(f"página {page.kind}")
            for key in sorted(MENU_KEYS):
                if needed(key):
                    publish_menu(key, user, note="E2E", expected_version=version(key))
                    self.stdout.write(key)
            if needed(brand.KEY):
                brand.publish(user, note="E2E", expected_version=version(brand.KEY))
                self.stdout.write(brand.KEY)
            from apps.cms.models import HomePublication

            if not HomePublication.objects.exists() or needed("home"):
                services.publish_home(user, note="E2E", expected_version=version("home"))
                self.stdout.write("home")
        self.stdout.write(self.style.SUCCESS("CMS publicado"))
