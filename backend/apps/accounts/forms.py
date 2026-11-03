from __future__ import annotations

from typing import Any

from django import forms
from django.contrib.auth.forms import PasswordResetForm
from django.db import transaction
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from unfold.forms import UserChangeForm, UserCreationForm
from unfold.widgets import UnfoldAdminSelectWidget

from apps.audit.services import record

from .roles import ROLE_PERMISSIONS


class AuditedPasswordResetForm(PasswordResetForm):
    @transaction.atomic
    def save(self, *args: Any, **kwargs: Any) -> None:
        request: HttpRequest | None = kwargs.get("request")
        # Do not record the submitted address or whether an account matched it.
        record("auth.password_reset_requested", request=request)
        super().save(*args, **kwargs)


class TeammateCreationForm(UserCreationForm):  # type: ignore[misc]
    role = forms.ChoiceField(
        label=_("Rol"),
        choices=[(role, role) for role in ROLE_PERMISSIONS],
        widget=UnfoldAdminSelectWidget,
        help_text=_(
            "Propietario: todo, incluido el equipo. Operaciones: pedidos, pagos, catálogo y "
            "cupones. Contenido: catálogo (sin precios) y página web."
        ),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["password1"].required = True
        self.fields["password2"].required = True
        # Team accounts always use a validated password in the single creation form.
        if "usable_password" in self.fields:
            del self.fields["usable_password"]


class TeammateChangeForm(UserChangeForm):  # type: ignore[misc]
    role = forms.ChoiceField(
        label=_("Rol"),
        choices=[(role, role) for role in ROLE_PERMISSIONS],
        widget=UnfoldAdminSelectWidget,
        help_text=_(
            "Propietario: todo, incluido el equipo. Operaciones: pedidos, pagos, catálogo y "
            "cupones. Contenido: catálogo (sin precios) y página web."
        ),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["role"].initial = (
                self.instance.groups.filter(name__in=ROLE_PERMISSIONS)
                .values_list("name", flat=True)
                .first()
            )
