from string import Formatter

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.accounts.roles import PROPIETARIO, has_role

from .models import SiteSettings


@transaction.atomic
def save_site_settings(obj: SiteSettings, *, actor: User | AnonymousUser) -> None:
    if not (actor.is_superuser or has_role(actor, PROPIETARIO)):
        raise PermissionDenied
    for field in ("general", "preorder", "reserved", "sold"):
        for locale in ("es", "en"):
            text = getattr(obj, f"whatsapp_{field}_{locale}")
            try:
                for _literal, name, spec, conversion in Formatter().parse(text):
                    if name is not None and (
                        name not in {"name", "sku", "url"} or spec or conversion
                    ):
                        raise ValueError
            except ValueError as exc:
                raise ValidationError(_("Solo se permiten {name}, {sku} y {url}.")) from exc
    obj.full_clean()
    obj.save()
