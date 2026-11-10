"""Sesión desechable: no permite elegir una cuenta existente."""

import json
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.auth.models import Group
from django.contrib.sessions.backends.db import SessionStore
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.roles import CONTENIDO, OPERACIONES, PROPIETARIO
from apps.accounts.services import sync_roles


class Command(BaseCommand):
    help = "Crea cuenta y cookie de panel efímeras para E2E (solo DEBUG)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--role", choices=[PROPIETARIO, CONTENIDO, OPERACIONES], default=PROPIETARIO
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Solo disponible con DEBUG=True.")
        if settings.ADMIN_2FA_REQUIRED:
            raise CommandError("E2E requiere el panel local sin segundo factor.")
        sync_roles()
        username = f"e2e-{uuid4().hex}"
        # Email is unique; no password is set, so the account cannot sign in by itself.
        user = User.objects.create_user(
            username=username, email=f"{username}@e2e.invalid", is_staff=True
        )
        user.groups.add(Group.objects.get(name=options["role"]))
        session = SessionStore()
        session[SESSION_KEY] = str(user.pk)
        session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
        session[HASH_SESSION_KEY] = user.get_session_auth_hash()
        session.set_expiry(3600)
        session.save()
        self.stdout.write(
            json.dumps(
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": session.session_key,
                    "admin_url": reverse("admin:orders_order_changelist"),
                }
            )
        )
