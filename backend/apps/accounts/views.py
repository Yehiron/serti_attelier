from __future__ import annotations

import base64
import io
from typing import Any

import qrcode
import qrcode.image.svg
from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.views import (
    INTERNAL_RESET_SESSION_TOKEN,
    PasswordChangeView,
    PasswordResetConfirmView,
)
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django_otp.plugins.otp_totp.models import TOTPDevice
from unfold.forms import AdminOwnPasswordChangeForm

from .selectors import confirmed_devices
from .services import change_password, setup_device, verify_device


class TokenForm(forms.Form):
    token = forms.CharField(
        label=_("Código de seis dígitos"),
        required=False,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}),
    )


def safe_next(request: HttpRequest) -> str:
    target = request.POST.get("next", request.GET.get("next", ""))
    if url_has_allowed_host_and_scheme(
        target, {request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return str("/" + settings.ADMIN_URL)


@never_cache
@sensitive_post_parameters("token")
@csrf_protect
@staff_member_required(login_url=reverse_lazy("admin:login"))  # type: ignore[untyped-decorator]  # Django decorator lacks typing.
def setup(request: HttpRequest) -> HttpResponse:
    if confirmed_devices(request.user).exists():
        return redirect("admin-2fa-verify")
    device = setup_device(request.user)
    return token_page(request, device, setup_mode=True)


@never_cache
@sensitive_post_parameters("token")
@csrf_protect
@staff_member_required(login_url=reverse_lazy("admin:login"))  # type: ignore[untyped-decorator]  # Django decorator lacks typing.
def verify(request: HttpRequest) -> HttpResponse:
    devices = confirmed_devices(request.user)
    device = devices.first()
    if device is None:
        return redirect("/" + settings.ADMIN_URL)
    return token_page(request, device, setup_mode=False)


def token_page(request: HttpRequest, device: TOTPDevice, *, setup_mode: bool) -> HttpResponse:
    form = TokenForm(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        valid_form = form.is_valid()
        token = form.cleaned_data.get("token", "") if valid_form else ""
        if verify_device(request, device.pk, token, setup=setup_mode):
            return redirect(safe_next(request))
        if valid_form:
            form.add_error("token", _("Código inválido. Espera unos segundos e intenta de nuevo."))
    context = {
        **admin.site.each_context(request),
        "form": form,
        "setup": setup_mode,
        "title": _("Configurar verificación en dos pasos") if setup_mode else _("Verificar acceso"),
        "next": safe_next(request),
    }
    if setup_mode:
        buffer = io.BytesIO()
        qrcode.make(device.config_url, image_factory=qrcode.image.svg.SvgPathImage).save(buffer)
        context["qr"] = buffer.getvalue().decode()
        context["secret"] = base64.b32encode(device.bin_key).decode()
    response = TemplateResponse(request, "admin/accounts/totp.html", context)
    response["Cache-Control"] = "no-store"
    return response


@method_decorator(sensitive_post_parameters(), name="dispatch")
class AuditedPasswordResetConfirmView(PasswordResetConfirmView):
    def form_valid(self, form: Any) -> HttpResponse:
        change_password(form, request=self.request)
        del self.request.session[INTERNAL_RESET_SESSION_TOKEN]
        return HttpResponseRedirect(self.get_success_url())


class AuditedPasswordChangeView(PasswordChangeView):
    form_class = AdminOwnPasswordChangeForm
    success_url = reverse_lazy("admin:password_change_done")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return {**super().get_context_data(**kwargs), **admin.site.each_context(self.request)}

    def form_valid(self, form: Any) -> HttpResponse:
        change_password(form, request=self.request, refresh_session=True)
        return HttpResponseRedirect(self.get_success_url())
