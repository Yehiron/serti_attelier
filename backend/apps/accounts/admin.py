from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from django_otp.plugins.otp_totp.models import TOTPDevice
from unfold.admin import ModelAdmin, TabularInline
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from apps.audit.services import record

from . import services
from .models import User

if TYPE_CHECKING:
    BaseUserAdmin = DjangoUserAdmin[User]
else:
    BaseUserAdmin = DjangoUserAdmin


class TeammateDeviceInline(TabularInline):  # type: ignore[misc]
    model = TOTPDevice
    fields = ("name", "confirmed")
    readonly_fields = fields
    extra = 0
    verbose_name = _("dispositivo de verificación")
    verbose_name_plural = _("Verificación en dos pasos: elimina el dispositivo para restablecerla")

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return request.user.has_perm("otp_totp.view_totpdevice")

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return request.user.has_perm("accounts.change_user") and request.user.has_perm(
            "otp_totp.delete_totpdevice"
        )


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):  # type: ignore[misc]  # Unfold has no stubs.
    def get_inlines(
        self, request: HttpRequest, obj: User | None = None
    ) -> tuple[type[TeammateDeviceInline], ...]:
        return (
            (TeammateDeviceInline,) if obj and TOTPDevice.objects.filter(user=obj).exists() else ()
        )

    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    add_fieldsets = (*DjangoUserAdmin.add_fieldsets, (None, {"fields": ("email",)}))

    def save_model(self, request: HttpRequest, obj: User, form: Any, change: bool) -> None:
        services.save_user(obj, request=request)

    def save_related(self, request: HttpRequest, form: Any, formsets: Any, change: bool) -> None:
        save = super().save_related
        services.save_related_user(
            form.instance, lambda: save(request, form, formsets, change), request=request
        )

    def save_formset(self, request: HttpRequest, form: Any, formset: Any, change: bool) -> None:
        if formset.model is TOTPDevice:
            formset.save(commit=False)
            for device in formset.deleted_objects:
                services.remove_device(device, request=request)
        else:
            super().save_formset(request, form, formset, change)

    def delete_model(self, request: HttpRequest, obj: User) -> None:
        services.delete_user(obj, request=request)

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[User]) -> None:
        for user in queryset:
            services.delete_user(user, request=request)

    def log_change(self, request: HttpRequest, obj: Any, message: Any) -> LogEntry:
        # Django's dedicated admin password form saves directly, bypassing save_model.
        if (
            request.resolver_match
            and request.resolver_match.url_name == "auth_user_password_change"
        ):
            record("auth.password_changed", actor=request.user, obj=obj, request=request)
        return super().log_change(request, obj, message)


admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(DjangoGroupAdmin, ModelAdmin):  # type: ignore[misc]  # Unfold has no stubs.
    def save_related(self, request: HttpRequest, form: Any, formsets: Any, change: bool) -> None:
        save = super().save_related
        services.save_related_group(
            form.instance, lambda: save(request, form, formsets, change), request=request
        )


admin.site.unregister(TOTPDevice)


@admin.register(TOTPDevice)
class DeviceAdmin(ModelAdmin):  # type: ignore[misc]  # Unfold has no stubs.
    list_display = ("user", "name", "confirmed")
    fields = ("user", "name", "confirmed")
    readonly_fields = fields

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def delete_model(self, request: HttpRequest, obj: TOTPDevice) -> None:
        services.remove_device(obj, request=request)

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[TOTPDevice]) -> None:
        for device in queryset:
            services.remove_device(device, request=request)
