from __future__ import annotations

from typing import Any, ClassVar
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin
from unfold.admin import ModelAdmin

from apps.core.admin import ReadOnlyAdmin
from apps.core.exceptions import DomainError

from . import services
from .forms import ContentForm
from .models import HomePublication, HomeSection, Page, PageRevision, PersonalizationService
from .preview import make_token
from .selectors import page_path


def preview_redirect(request: HttpRequest, target: str) -> HttpResponseRedirect:
    query = urlencode({"token": make_token(request.user), "path": target})  # type: ignore[arg-type]
    return HttpResponseRedirect(f"{settings.PUBLIC_SITE_URL}/preview?{query}")


class ContentAdmin(TabbedTranslationAdmin[Any], ModelAdmin):  # type: ignore[misc]
    form: Any = ContentForm
    readonly_fields: ClassVar[tuple[str, ...]] = ("created_at", "updated_at")

    def has_publish_permission(self, request: HttpRequest) -> bool:
        return request.user.has_perm("cms.publish_content")

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(HomeSection)
class HomeSectionAdmin(ContentAdmin):
    list_display = ("kind", "title", "position", "is_visible")
    ordering = ("position", "pk")
    readonly_fields = (*ContentAdmin.readonly_fields, "renditions", "width", "height")
    change_list_template = "admin/cms/home_changelist.html"

    def get_urls(self) -> list[Any]:
        return [
            path("preview/", self.admin_site.admin_view(self.preview), name="cms-home-preview"),
            path("publish/", self.admin_site.admin_view(self.publish), name="cms-home-publish"),
            *super().get_urls(),
        ]

    def preview(self, request: HttpRequest) -> HttpResponse:
        if not self.has_change_permission(request):
            raise PermissionDenied
        return preview_redirect(request, "/es")

    def publish(self, request: HttpRequest) -> HttpResponse:
        if request.method != "POST" or not self.has_publish_permission(request):
            raise PermissionDenied
        try:
            services.publish_home(request.user, request)
            self.message_user(request, _("Inicio publicado."), messages.SUCCESS)
        except (ValidationError, DomainError) as exc:
            self.message_user(request, str(exc), messages.ERROR)
        return HttpResponseRedirect(reverse("admin:cms_homesection_changelist"))

    def changelist_view(
        self, request: HttpRequest, extra_context: dict[str, Any] | None = None
    ) -> Any:
        return super().changelist_view(
            request,
            {
                **(extra_context or {}),
                "can_preview": self.has_change_permission(request),
                "can_publish": self.has_publish_permission(request),
            },
        )

    def save_model(self, request: HttpRequest, obj: HomeSection, form: Any, change: bool) -> None:
        services.save_section(obj)


@admin.register(Page)
class PageAdmin(ContentAdmin):
    list_display = ("title", "kind", "status", "version")
    readonly_fields = (
        *ContentAdmin.readonly_fields,
        "status",
        "version",
        "published_at",
        "preview_link",
    )
    actions = ("publish",)

    def get_urls(self) -> list[Any]:
        return [
            path(
                "<int:object_id>/preview/",
                self.admin_site.admin_view(self.preview),
                name="cms-page-preview",
            ),
            *super().get_urls(),
        ]

    def preview(self, request: HttpRequest, object_id: int) -> HttpResponse:
        obj = self.get_object(request, str(object_id))
        if obj is None or not self.has_change_permission(request, obj):
            raise PermissionDenied
        return preview_redirect(request, page_path(obj.kind, "es", obj.slug_es, obj.slug_en))

    def get_readonly_fields(self, request: HttpRequest, obj: Page | None = None) -> tuple[str, ...]:
        return (
            self.readonly_fields
            if self.has_change_permission(request, obj)
            else tuple(field for field in self.readonly_fields if field != "preview_link")
        )

    @admin.display(description=_("Vista previa"))
    def preview_link(self, obj: Page) -> str:
        if not obj.pk:
            return str(_("Guarda el borrador para abrir la vista previa."))
        return format_html(
            '<a href="{}">{}</a>',
            reverse("admin:cms-page-preview", args=[obj.pk]),
            _("Vista previa"),
        )

    def save_model(self, request: HttpRequest, obj: Page, form: Any, change: bool) -> None:
        services.save_page(obj)

    @admin.action(description=_("Publicar"), permissions=["publish"])
    def publish(self, request: HttpRequest, queryset: QuerySet[Page]) -> None:
        for page in queryset:
            services.publish_page(page, request.user, request)


@admin.register(PersonalizationService)
class PersonalizationAdmin(ContentAdmin):
    list_display = ("title", "position", "is_active")
    readonly_fields = (*ContentAdmin.readonly_fields, "renditions", "width", "height")

    def save_model(
        self, request: HttpRequest, obj: PersonalizationService, form: Any, change: bool
    ) -> None:
        services.save_personalization(obj)


@admin.register(HomePublication, PageRevision)
class PublicationAdmin(ReadOnlyAdmin):
    list_display = ("__str__", "published_at", "published_by_repr")
    actions = ("restore",)

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return bool(request.user.has_perm(f"cms.view_{self.model._meta.model_name}"))

    def has_publish_permission(self, request: HttpRequest) -> bool:
        return request.user.has_perm("cms.publish_content")

    @admin.action(description=_("Restaurar como borrador"), permissions=["publish"])
    def restore(self, request: HttpRequest, queryset: QuerySet[Any]) -> None:
        if queryset.count() != 1:
            self.message_user(request, _("Selecciona una sola publicación."), messages.ERROR)
            return
        obj = queryset.get()
        if isinstance(obj, HomePublication):
            services.restore_home(obj, request.user, request)
        else:
            services.restore_page_revision(obj, request.user, request)
