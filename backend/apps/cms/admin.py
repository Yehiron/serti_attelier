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
from modeltranslation.admin import TabbedTranslationAdmin, TranslationTabularInline
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action

from apps.core.admin import ReadOnlyAdmin
from apps.core.admin_presentation import ClientPresentationMixin
from apps.core.exceptions import DomainError

from . import services
from .forms import ContentForm, DesktopSlideForm, MobileSlideForm, PhotoInput
from .models import (
    HeroSlide,
    HomePublication,
    HomeSection,
    Page,
    PageRevision,
    PersonalizationService,
)
from .preview import make_token
from .selectors import draft_sections, page_path, render_sections


def preview_redirect(request: HttpRequest, target: str) -> HttpResponseRedirect:
    query = urlencode({"token": make_token(request.user), "path": target})  # type: ignore[arg-type]
    return HttpResponseRedirect(f"{settings.PUBLIC_SITE_URL}/preview?{query}")


class ContentAdmin(ClientPresentationMixin, TabbedTranslationAdmin[Any], ModelAdmin):  # type: ignore[misc]
    form: Any = ContentForm
    readonly_fields: ClassVar[tuple[str, ...]] = ("created_at", "updated_at")

    def has_publish_permission(self, request: HttpRequest, object_id: Any = None) -> bool:
        return request.user.has_perm("cms.publish_content")

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


class HeroSlideInline(TranslationTabularInline[HeroSlide, HomeSection], TabularInline):  # type: ignore[misc]
    ordering_field = "position"
    hide_ordering_field = True
    model = HeroSlide
    form: Any = DesktopSlideForm
    device = HeroSlide.Device.DESKTOP
    extra = 0
    ordering = ("position", "pk")
    fields = ("position", "image", "previews", "alt", "image_status")
    readonly_fields = ("previews", "image_status")
    image_status = ClientPresentationMixin.image_status
    verbose_name = _("foto para computador")
    verbose_name_plural = _("Fotos para computador (horizontales)")
    template_before = "admin/cms/slide_description.html"
    description = _("Se muestran en computadores y tabletas. Medida recomendada: 1920 × 900 px.")  # noqa: RUF001

    def get_queryset(self, request: HttpRequest) -> QuerySet[HeroSlide]:
        return super().get_queryset(request).filter(device=self.device)

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return request.user.has_perm("cms.view_homesection")

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return request.user.has_perm("cms.change_homesection")

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return request.user.has_perm("cms.change_homesection")

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return request.user.has_perm("cms.change_homesection")

    @admin.display(description=_("Vista previa"))
    def previews(self, obj: HeroSlide) -> str:
        if not obj.image:
            return "—"
        width, height = (80, 107) if self.device == HeroSlide.Device.MOBILE else (200, 94)
        return format_html(
            '<img src="{}" style="width:{}px;height:{}px;object-fit:contain" alt="">',
            obj.image.url,
            width,
            height,
        )


class MobileHeroSlideInline(HeroSlideInline):
    form = MobileSlideForm
    device = HeroSlide.Device.MOBILE
    verbose_name = _("foto para celular")
    verbose_name_plural = _("Fotos para celular (verticales)")
    description = _("Se muestran en celulares. Medida recomendada: 1080 × 1350 px (vertical).")  # noqa: RUF001


@admin.register(HomeSection)
class HomeSectionAdmin(ContentAdmin):
    ordering_field = "position"
    hide_ordering_field = True
    list_display = ("kind", "title", "position", "is_visible")
    ordering = ("position", "pk")
    readonly_fields = (*ContentAdmin.readonly_fields, "image_preview", "image_status")
    change_list_template = "admin/cms/home_changelist.html"

    change_form_template = "admin/cms/home_changeform.html"
    change_form_before_template = "admin/cms/home_save_publish.html"
    conditional_fields = {
        f"cta_{target}": f"cta_kind == '{target}'"
        for target in ("category", "stone", "collection", "piece", "page")
    } | {"cta_external_url": "cta_kind == 'external'"}

    def has_add_permission(self, request: HttpRequest) -> bool:
        return bool(request.user.is_superuser and super().has_add_permission(request))

    def get_readonly_fields(
        self, request: HttpRequest, obj: HomeSection | None = None
    ) -> tuple[str, ...]:
        return (*self.readonly_fields, "kind") if obj else self.readonly_fields

    def get_fieldsets(self, request: HttpRequest, obj: HomeSection | None = None) -> Any:
        kind = obj.kind if obj else "hero"
        fields = ["kind", "is_visible", "title"]
        if kind in {"hero", "stone_panels", "collection_rail"}:
            fields.append("subtitle")
        if kind in {"statement", "story", "personalize", "banner"}:
            fields.append("body")
        if kind in {"story", "personalize", "banner"}:
            fields.extend(["image", "image_preview", "image_alt", "image_status"])
        if kind == "collection_rail":
            fields.append("collection")
        if kind in {"hero", "story", "personalize", "banner"}:
            fields.extend(
                [
                    "cta_label",
                    "cta_kind",
                    "cta_category",
                    "cta_stone",
                    "cta_collection",
                    "cta_piece",
                    "cta_page",
                    "cta_external_url",
                ]
            )
        return [
            (None, {"fields": self.replace_orig_field(fields)}),
            (_("Orden"), {"fields": ["position"], "classes": ["collapse"]}),
        ]

    def get_form(
        self, request: HttpRequest, obj: Any = None, change: bool = False, **kwargs: Any
    ) -> Any:
        form = super().get_form(request, obj, change=change, **kwargs)
        if "image" in form.base_fields:
            form.base_fields["image"].widget = PhotoInput()
        for field in form.base_fields.values():
            if hasattr(field, "empty_label"):
                field.empty_label = _("Selecciona una opción")
            field.widget.attrs["data-placeholder"] = _("Selecciona una opción")
        return form

    def publication_context(self, request: HttpRequest) -> dict[str, Any]:
        latest = HomePublication.objects.first()
        sections = list(draft_sections())
        snapshot = {locale: render_sections(sections, locale) for locale in ("es", "en")}
        return {
            "pending_home_changes": latest is None
            or latest.snapshot != snapshot
            or latest.draft_snapshot != [services.section_source(section) for section in sections],
            "last_home_publication": latest,
            "can_preview": self.has_change_permission(request),
            "can_publish": self.has_publish_permission(request),
        }

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> Any:
        return super().change_view(
            request,
            object_id,
            form_url,
            {
                **(extra_context or {}),
                **self.publication_context(request),
                "home_return_to": reverse("admin:cms_homesection_change", args=[object_id]),
            },
        )

    def response_change(self, request: HttpRequest, obj: HomeSection) -> HttpResponse:
        if "_savepublish" in request.POST:
            if not self.has_publish_permission(request):
                raise PermissionDenied
            try:
                services.publish_home(request.user, request)
                self.message_user(request, _("Inicio publicado."), messages.SUCCESS)
            except (ValidationError, DomainError) as exc:
                self.message_user(request, str(exc), messages.ERROR)
            return HttpResponseRedirect(reverse("admin:cms_homesection_change", args=[obj.pk]))
        return super().response_change(request, obj)

    def get_inlines(
        self, request: HttpRequest, obj: HomeSection | None = None
    ) -> tuple[type[HeroSlideInline], ...]:
        return (HeroSlideInline, MobileHeroSlideInline) if obj and obj.kind == "hero" else ()

    def save_formset(self, request: HttpRequest, form: Any, formset: Any, change: bool) -> None:
        instances = formset.save(commit=False)
        for deleted in formset.deleted_objects:
            services.delete_hero_slide(deleted)
        for instance in instances:
            services.save_hero_slide(instance)
        formset.save_m2m()

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
        section_id = request.POST.get("section_id", "")
        if section_id.isdecimal() and HomeSection.objects.filter(pk=section_id).exists():
            return HttpResponseRedirect(reverse("admin:cms_homesection_change", args=[section_id]))
        return HttpResponseRedirect(reverse("admin:cms_homesection_changelist"))

    def changelist_view(
        self, request: HttpRequest, extra_context: dict[str, Any] | None = None
    ) -> Any:
        return super().changelist_view(
            request,
            {
                **(extra_context or {}),
                **self.publication_context(request),
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
    actions_detail = ("detail_preview", "detail_publish")
    change_form_before_template = "admin/cms/page_status.html"

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> Any:
        page = self.get_object(request, object_id)
        revision = page.revisions.first() if page else None
        pending = not revision or any(
            revision.snapshot[locale].get("source", {}).get(field)
            != getattr(page, f"{field}_{locale}")
            for locale in ("es", "en")
            for field in ("title", "slug", "body")
        )
        return super().change_view(
            request, object_id, form_url, {**(extra_context or {}), "pending_page_changes": pending}
        )

    @action(
        description=_("Vista previa"),
        permissions=["change"],
        attrs={"target": "_blank", "rel": "noopener"},
    )  # type: ignore[untyped-decorator]
    def detail_preview(self, request: HttpRequest, object_id: str) -> HttpResponse:
        return self.preview(request, int(object_id))

    @action(description=_("Publicar"), permissions=["publish", "change"])  # type: ignore[untyped-decorator]
    def detail_publish(self, request: HttpRequest, object_id: str) -> HttpResponse:
        page = self.get_object(request, object_id)
        if page is None or not self.has_change_permission(request, page):
            raise PermissionDenied
        back_url = reverse("admin:cms_page_change", args=[object_id])
        if request.method != "POST":
            from django.template.response import TemplateResponse

            return TemplateResponse(
                request,
                "admin/catalog/confirm_action.html",
                {
                    **self.admin_site.each_context(request),
                    "title": _("Publicar"),
                    "original": page,
                    "back_url": back_url,
                },
            )
        try:
            services.publish_page(page, request.user, request)
            self.message_user(request, _("Página publicada."), messages.SUCCESS)
        except (DomainError, ValidationError) as exc:
            self.message_user(request, str(exc), messages.ERROR)
        return HttpResponseRedirect(back_url)

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
    ordering_field = "position"
    hide_ordering_field = True
    list_display = ("title", "position", "is_active")
    readonly_fields = (*ContentAdmin.readonly_fields, "image_preview", "image_status")

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

    def has_publish_permission(self, request: HttpRequest, object_id: Any = None) -> bool:
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
