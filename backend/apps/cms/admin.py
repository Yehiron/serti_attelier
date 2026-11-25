from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import urlencode

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
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

from . import services
from .documents import (
    ContentConflict,
    admin_batch,
    document_key,
    get_document,
    lock_document,
    require_capability,
    validate_admin_version,
)
from .forms import ContentForm, DesktopSlideForm, MobileSlideForm, PhotoInput
from .models import (
    FaqItem,
    HeroSlide,
    HomePublication,
    HomeSection,
    Page,
    PageRevision,
    PersonalizationService,
    ProcessStep,
)
from .preview import make_token
from .publishing import pending_changes
from .selectors import page_path


def preview_redirect(request: HttpRequest, target: str) -> HttpResponseRedirect:
    require_capability(request.user, "preview")
    query = urlencode({"token": make_token(request.user), "path": target})  # type: ignore[arg-type]
    return HttpResponseRedirect(f"{settings.PUBLIC_SITE_URL}/preview?{query}")


class ContentAdmin(ClientPresentationMixin, TabbedTranslationAdmin[Any], ModelAdmin):  # type: ignore[misc]
    form: Any = ContentForm
    readonly_fields: ClassVar[tuple[str, ...]] = ("created_at", "updated_at")

    def has_module_permission(self, request):
        return request.user.has_perm("cms.edit_content") and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("cms.edit_content") and super().has_view_permission(
            request, obj
        )

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("cms.edit_content") and super().has_change_permission(
            request, obj
        )

    def has_add_permission(self, request):
        return request.user.has_perm("cms.edit_content") and super().has_add_permission(request)

    def _changeform_view(self, request, object_id, form_url, extra_context):
        if "_savepublish" in request.POST:
            require_capability(request.user, "publish")
        with transaction.atomic(), admin_batch():
            if self.model in (HomeSection, Page):
                if self.model is HomeSection:
                    key = "home"
                else:
                    kind = (
                        Page.objects.filter(pk=object_id).values_list("kind", flat=True).first()
                        if object_id
                        else request.POST.get("kind", "contact")
                    )
                    key = f"page:{kind}"
                lock_document(key)
            response = super()._changeform_view(request, object_id, form_url, extra_context)
            # Inline querysets and widgets must be evaluated under the same lock as the version.
            if hasattr(response, "render"):
                response.render()
            return response

    def get_form(self, request, obj=None, change=False, **kwargs):
        base = super().get_form(request, obj, change=change, **kwargs)
        if self.model not in (HomeSection, Page):
            return base
        return self.versioned_form(request, base, obj)

    def versioned_form(self, request, base, obj=None):
        key = (
            document_key(obj)
            if obj
            else (
                "home"
                if self.model is HomeSection
                else "page:" + request.POST.get("kind", "contact")
            )
        )
        version = get_document(key).draft_version
        url = request.path

        class VersionedForm(base):  # type: ignore[valid-type, misc]  # Runtime-generated form subclass.
            expected_version = forms.IntegerField(
                min_value=0, initial=version, widget=forms.HiddenInput
            )

            def clean(self):
                data = super().clean()
                if self.is_bound and "expected_version" in data:
                    try:
                        validate_admin_version(key, data["expected_version"])
                    except ContentConflict as exc:
                        self.add_error(
                            None,
                            format_html(
                                '{} <a href="{}" target="_blank" rel="noopener">'
                                "Ver versión actual</a>",
                                " ".join(exc.messages),
                                url,
                            ),
                        )
                return data

        return VersionedForm

    def has_publish_permission(self, request: HttpRequest, object_id: Any = None) -> bool:
        return request.user.has_perm("cms.publish_content")

    def has_preview_permission(self, request, object_id=None):
        return request.user.has_perm("cms.preview_content")

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
        kind = obj.kind if obj else request.POST.get("kind", request.GET.get("kind", "hero"))
        fields = ["expected_version", "kind", "is_visible", "title"]
        from .registry import REGISTRY

        spec = REGISTRY.get(kind, REGISTRY["hero"])
        if spec.storage != "columns":
            fields = ["expected_version", "kind", "is_visible", "props"]
        else:
            keys = {field.key for field in spec.fields}
            fields.extend(key for key in ("subtitle", "body", "collection") if key in keys)
            if "image" in keys and kind != "hero":
                fields.extend(["image", "image_preview", "image_alt", "image_status"])
            if "cta" in keys:
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
        pending = pending_changes("home", previous=latest)
        return {
            "pending_home_changes": bool(pending["count"]),
            "pending_count": pending["count"],
            "draft_version": get_document("home").draft_version,
            "last_home_publication": latest,
            "can_preview": request.user.has_perm("cms.preview_content"),
            "can_publish": self.has_publish_permission(request),
            "review_url": reverse("cms-review-publish", args=["home"]),
        }

    @transaction.atomic
    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> Any:
        lock_document("home")
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

    def response_change(self, request, obj):
        if "_savepublish" in request.POST:
            return HttpResponseRedirect(reverse("cms-review-publish", args=["home"]))
        return super().response_change(request, obj)

    def get_inlines(
        self, request: HttpRequest, obj: HomeSection | None = None
    ) -> tuple[type[HeroSlideInline], ...]:
        return (HeroSlideInline, MobileHeroSlideInline) if obj and obj.kind == "hero" else ()

    def save_formset(self, request: HttpRequest, form: Any, formset: Any, change: bool) -> None:
        instances = formset.save(commit=False)
        for deleted in formset.deleted_objects:
            services.delete_hero_slide(deleted, actor=request.user, request=request)
        for instance in instances:
            services.save_hero_slide(instance, actor=request.user, request=request)
        formset.save_m2m()

    def get_urls(self) -> list[Any]:
        return [
            path("preview/", self.admin_site.admin_view(self.preview), name="cms-home-preview"),
            path("publish/", self.admin_site.admin_view(self.publish), name="cms-home-publish"),
            *super().get_urls(),
        ]

    def preview(self, request: HttpRequest) -> HttpResponse:
        require_capability(request.user, "preview")
        return preview_redirect(request, "/es")

    def publish(self, request: HttpRequest) -> HttpResponse:
        require_capability(request.user, "publish")
        return HttpResponseRedirect(reverse("cms-review-publish", args=["home"]))

    def get_changelist_form(self, request, **kwargs):
        base = super().get_changelist_form(request, **kwargs)
        return self.versioned_form(request, base)

    @transaction.atomic
    def changelist_view(
        self, request: HttpRequest, extra_context: dict[str, Any] | None = None
    ) -> Any:
        with admin_batch():
            lock_document("home")
            response = super().changelist_view(
                request,
                {
                    **(extra_context or {}),
                    **self.publication_context(request),
                },
            )
            if hasattr(response, "render"):
                response.render()
            return response

    def save_model(self, request: HttpRequest, obj: HomeSection, form: Any, change: bool) -> None:
        services.save_section(
            obj,
            actor=request.user,
            request=request,
            **(
                {"expected_version": form.cleaned_data.get("expected_version")}
                if form is not None
                else {}
            ),
        )


if TYPE_CHECKING:
    _TranslationInlineBase = TranslationTabularInline[Any, Any]
else:
    _TranslationInlineBase = TranslationTabularInline


class PageItemInline(_TranslationInlineBase, TabularInline):  # type: ignore[misc]  # Unfold has no stubs.
    ordering_field = "position"
    hide_ordering_field = False
    extra = 0

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("cms.view_page")

    def has_add_permission(self, request, obj=None):
        return request.user.has_perm("cms.change_page")

    has_change_permission = has_add_permission
    has_delete_permission = has_add_permission

    class Media:
        js = ("cms/character-count.js",)


class ProcessStepInline(PageItemInline):
    from .registry import REGISTRY

    max_num = next(field.max for field in REGISTRY["process"].fields if field.type == "list")
    model = ProcessStep
    fields = ("position", "title", "description")


class FaqItemInline(PageItemInline):
    from .registry import REGISTRY

    max_num = next(field.max for field in REGISTRY["faq"].fields if field.type == "list")
    model = FaqItem
    fields = ("position", "question", "answer")


@admin.register(Page)
class PageAdmin(ContentAdmin):
    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

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

    class Media:
        js = ("cms/character-count.js",)

    def get_inlines(self, request, obj=None):
        if obj and obj.kind == "personalize":
            return (ProcessStepInline, FaqItemInline)
        return (FaqItemInline,) if obj else ()

    def get_fieldsets(self, request, obj=None):
        fields = ["expected_version", "kind", "title", "slug"]
        description = ""
        if obj and obj.kind == "personalize":
            fields += ["process_title", "faq_title"]
            description = "Esta página muestra los pasos y las preguntas frecuentes de abajo."
        else:
            fields += ["body", "faq_title"]
        return [
            (None, {"fields": self.replace_orig_field(fields), "description": description}),
            (
                "Publicación",
                {
                    "fields": ["status", "version", "published_at"]
                    + (["preview_link"] if request.user.has_perm("cms.preview_content") else [])
                },
            ),
        ]

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            services.delete_page_item(obj, actor=request.user, request=request)
        for obj in instances:
            services.save_page_item(obj, actor=request.user, request=request)
        formset.save_m2m()

    @transaction.atomic
    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> Any:
        page = self.get_object(request, object_id)
        if page:
            lock_document(document_key(page))
        pending = pending_changes(document_key(page)) if page else {"count": 0}
        return super().change_view(
            request,
            object_id,
            form_url,
            {
                **(extra_context or {}),
                "pending_page_changes": bool(pending["count"]),
                "pending_count": pending["count"],
                "can_publish": self.has_publish_permission(request),
                "review_url": reverse("cms-review-publish", args=[document_key(page)])
                if page
                else "",
            },
        )

    @action(
        description=_("Vista previa"),
        permissions=["preview"],
        attrs={"target": "_blank", "rel": "noopener"},
    )  # type: ignore[untyped-decorator]
    def detail_preview(self, request: HttpRequest, object_id: str) -> HttpResponse:
        return self.preview(request, int(object_id))

    @action(description=_("Revisar y publicar"), permissions=["publish", "change"])  # type: ignore[untyped-decorator]
    def detail_publish(self, request: HttpRequest, object_id: str) -> HttpResponse:
        require_capability(request.user, "publish")
        page = self.get_object(request, object_id)
        if page is None:
            raise PermissionDenied
        return HttpResponseRedirect(reverse("cms-review-publish", args=[document_key(page)]))

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
        require_capability(request.user, "preview")
        obj = self.get_object(request, str(object_id))
        if obj is None:
            raise PermissionDenied
        return preview_redirect(request, page_path(obj.kind, "es", obj.slug_es, obj.slug_en))

    def get_readonly_fields(self, request: HttpRequest, obj: Page | None = None) -> tuple[str, ...]:
        return (*self.readonly_fields, "kind") if obj else self.readonly_fields

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
        services.save_page(
            obj,
            actor=request.user,
            request=request,
            **(
                {"expected_version": form.cleaned_data.get("expected_version")}
                if form is not None
                else {}
            ),
        )

    @admin.action(description=_("Revisar y publicar"), permissions=["publish"])
    def publish(self, request: HttpRequest, queryset: QuerySet[Page]) -> HttpResponse:
        require_capability(request.user, "publish")
        if queryset.count() != 1:
            self.message_user(
                request, _("Selecciona una sola página para revisar."), messages.ERROR
            )
            return HttpResponseRedirect(request.path)
        return HttpResponseRedirect(
            reverse("cms-review-publish", args=[document_key(queryset.get())])
        )


@admin.register(PersonalizationService)
class PersonalizationAdmin(ContentAdmin):
    ordering_field = "position"
    hide_ordering_field = True
    list_display = ("title", "position", "is_active")
    readonly_fields = (*ContentAdmin.readonly_fields, "image_preview", "image_status")

    def save_model(
        self, request: HttpRequest, obj: PersonalizationService, form: Any, change: bool
    ) -> None:
        services.save_personalization(obj, actor=request.user)


@admin.register(HomePublication, PageRevision)
class PublicationAdmin(ReadOnlyAdmin):
    list_display = ("__str__", "published_at", "published_by_repr")
    actions = ("restore",)

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return bool(request.user.has_perm(f"cms.view_{self.model._meta.model_name}"))

    def has_publish_permission(self, request: HttpRequest, object_id: Any = None) -> bool:
        return request.user.has_perm("cms.publish_content")

    def has_restore_permission(self, request, object_id=None):
        return request.user.has_perm("cms.restore_content")

    @admin.action(description=_("Restaurar como borrador"), permissions=["restore"])
    def restore(self, request: HttpRequest, queryset: QuerySet[Any]) -> HttpResponseRedirect | None:
        if queryset.count() != 1:
            self.message_user(request, _("Selecciona una sola publicación."), messages.ERROR)
            return None
        obj = queryset.get()
        key = "home" if isinstance(obj, HomePublication) else f"page:{obj.page.kind}"
        return HttpResponseRedirect(reverse("cms-history") + f"?document={key}&restore={obj.pk}")
