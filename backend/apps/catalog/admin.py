from __future__ import annotations

from collections.abc import Sequence
from copy import copy
from typing import Any, ClassVar, cast
from urllib.parse import quote

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.actions import delete_selected
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import (
    Case,
    Count,
    Exists,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    QuerySet,
    When,
)
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.decorators import method_decorator
from django.utils.html import format_html, format_html_join, strip_tags
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_POST
from modeltranslation.admin import (
    TabbedTranslationAdmin,
    TranslationAdmin,
    TranslationTabularInline,
)
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action

from apps.core.admin_presentation import ClientPresentationMixin, thumbnail_url
from apps.core.admin_selection import OptionalSelectionMixin
from apps.core.exceptions import DomainError
from apps.core.formatting import format_admin_cop
from apps.core.selectors import piece_url
from apps.inventory.services import set_preorder

from . import services
from .audit_history import CatalogAuditHistoryMixin
from .forms import (
    CategoryForm,
    PieceForm,
    PieceImageForm,
    PieceImageFormSet,
    PieceVideoForm,
    QuickCategoryForm,
    ValidatedImageForm,
)
from .models import (
    Category,
    Collection,
    CollectionPiece,
    Material,
    Piece,
    PieceImage,
    PieceVideo,
    Stone,
)
from .selectors import missing_english_translation


def deletion_icon(obj, reason, label):
    if reason:
        return format_html(
            '<span class="ca-icon ca-danger" role="link" tabindex="0" aria-disabled="true" '
            'aria-label="{}" title="{}" aria-description="{}">'
            '<span class="material-symbols-outlined" '
            'aria-hidden="true">delete</span></span>',
            label,
            "No se puede eliminar: " + reason + (". Archívala." if isinstance(obj, Piece) else ""),
            reason,
        )
    return format_html(
        '<a class="ca-icon ca-danger" href="{}" aria-label="{}" title="{}">'
        '<span class="material-symbols-outlined" aria-hidden="true">delete</span></a>',
        reverse(f"admin:catalog_{obj._meta.model_name}_delete", args=[obj.pk]),
        label,
        label,
    )


class TranslatedAdmin(
    CatalogAuditHistoryMixin,
    ClientPresentationMixin,
    TabbedTranslationAdmin[Any],
    ModelAdmin,  # type: ignore[misc]  # Unfold has no stubs.
):
    prepopulated_fields = {"slug": ("name",)}
    search_fields: ClassVar[tuple[str, ...]] = ("name_es", "name_en")
    list_display: tuple[str, ...] = ("name", "position")
    form: Any = ValidatedImageForm
    ordering_field: str | None = "position"
    hide_ordering_field = True
    readonly_fields: ClassVar[tuple[str, ...]] = ("image_preview", "image_status")

    class Media:
        css = {"all": ("catalog/catalog-admin.css",)}

    def get_actions(self, request, *args, **kwargs):
        return super().get_actions(request) if self.model is Material else {}

    delete_confirmation_template = "admin/catalog/delete_confirmation.html"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if self.model in (Stone, Collection):
            qs = qs.annotate(deletion_piece_count=Count("pieces", distinct=True))
        return qs

    def get_list_display(self, request):
        fields = super().get_list_display(request)
        if isinstance(self, CategoryAdmin) or self.model is Material:
            return fields
        return (*fields, self.delete_action(request))

    def delete_action(self, request):
        @admin.display(description="Eliminar")
        def delete_icon(obj):
            if not self.has_delete_permission(request):
                return ""
            reason = services.taxonomy_deletion_reason(obj)
            return deletion_icon(obj, reason, "Eliminar " + str(obj._meta.verbose_name))

        return delete_icon

    def get_deleted_objects(self, objs, request):
        deleted, counts, perms, protected = super().get_deleted_objects(objs, request)
        protected.extend(
            reason for obj in objs if (reason := services.taxonomy_deletion_reason(obj))
        )
        return deleted, counts, perms, protected

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:
        services.save_taxonomy(obj, actor=request.user, request=request)

    def delete_model(self, request: HttpRequest, obj: Any) -> None:
        services.delete_catalog_object(obj, actor=request.user, request=request)

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> None:
        for obj in queryset:
            services.delete_catalog_object(obj, actor=request.user, request=request)


@admin.register(Category)
class CategoryAdmin(TranslatedAdmin):
    form = CategoryForm
    ordering_field = "position"
    list_display = (
        "category_photo",
        "hierarchical_name",
        "parent",
        "published_count",
        "active_badge",
        "category_actions",
        "position",
    )
    list_display_links = ("hierarchical_name",)
    change_list_template = "admin/catalog/category/change_list.html"

    class Media:
        css = {"all": ("catalog/catalog-admin.css",)}

    def get_list_display(self, request):
        @admin.display(description="Acciones")
        def actions(obj):
            return format_html(
                '<div class="ca-actions">{}{}</div>',
                self.category_actions(obj),
                self.delete_action(request)(obj),
            )

        return tuple(
            actions if field == "category_actions" else field for field in self.list_display
        )

    def get_ordering(self, request):
        return (
            Coalesce("parent__position", "position"),
            Coalesce("parent_id", "pk"),
            Case(When(parent=None, then=0), default=1, output_field=IntegerField()),
            "position",
            "pk",
        )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("parent")
            .annotate(
                published_total=Count(
                    "pieces", filter=Q(pieces__status=Piece.Status.PUBLISHED), distinct=True
                ),
                deletion_piece_count=Count("pieces", distinct=True),
                deletion_child_count=Count("children", distinct=True),
                root_position=Coalesce("parent__position", "position"),
                root_id=Coalesce("parent_id", "pk"),
                hierarchy_level=Case(
                    When(parent=None, then=0), default=1, output_field=IntegerField()
                ),
            )
            .order_by("root_position", "root_id", "hierarchy_level", "position", "pk")
        )

    @admin.display(description="Foto")
    def category_photo(self, obj):
        paths = obj.cover_renditions.get("webp", {})
        src = (
            default_storage.url(paths[min(paths, key=int)])
            if paths
            else (obj.cover_image.url if obj.cover_image else "")
        )
        return format_html('<img class="ca-thumb" src="{}" alt="">', src) if src else "—"

    @admin.display(description="Nombre")
    def hierarchical_name(self, obj):
        return (
            format_html('<span class="ca-child">↳ {}</span>', obj.name_es)
            if obj.parent_id
            else format_html("<strong>{}</strong>", obj.name_es)
        )

    @admin.display(description="Piezas publicadas")
    def published_count(self, obj):
        return obj.published_total

    @admin.display(description="Activa")
    def active_badge(self, obj):
        return format_html(
            '<span class="ca-badge">{}</span>',
            (
                "Visible en la tienda · sin piezas publicadas"
                if not obj.published_total
                else "Visible en la tienda"
            )
            if obj.is_active
            else "No visible en la tienda: inactiva",
        )

    @admin.display(description="Acciones")
    def category_actions(self, obj):
        edit = format_html(
            '<a class="ca-icon" href="{}" aria-label="Editar" title="Editar">'
            '<span class="material-symbols-outlined" aria-hidden="true">edit</span></a>',
            reverse("admin:catalog_category_change", args=[obj.pk]),
        )
        view = (
            format_html(
                '<a class="ca-icon" href="{}/es/joyeria/{}" target="_blank" rel="noopener" '
                'aria-label="Ver en la tienda" title="Ver en la tienda">'
                '<span class="material-symbols-outlined" aria-hidden="true">open_in_new</span></a>',
                settings.PUBLIC_SITE_URL.rstrip("/"),
                quote(obj.slug_es),
            )
            if obj.is_active
            else ""
        )
        return format_html('<div class="ca-actions">{}{}</div>', edit, view)

    def get_urls(self):
        return [
            path(
                "quick-add/",
                self.admin_site.admin_view(self.quick_add),
                name="catalog_category_quick_add",
            ),
            *super().get_urls(),
        ]

    @method_decorator(require_POST)
    def quick_add(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied
        form = QuickCategoryForm(request.POST)
        if form.is_valid():
            obj = Category(name_es=form.cleaned_data["name"], parent=form.cleaned_data["parent"])
            try:
                with transaction.atomic():
                    services.save_taxonomy(obj, actor=request.user, request=request)
            except ValidationError as exc:
                for field, errors in (
                    exc.message_dict if hasattr(exc, "message_dict") else {"__all__": exc.messages}
                ).items():
                    form.add_error(
                        "name"
                        if field in ("name", "name_es", "slug_es")
                        else field
                        if field in form.fields
                        else None,
                        errors,
                    )
            else:
                label = (
                    f"{cast(Category, obj.parent).name_es} → {obj.name_es}"
                    if obj.parent_id
                    else obj.name_es
                )
                return JsonResponse({"id": obj.pk, "label": label})
        return JsonResponse({"errors": dict(form.errors)}, status=400)


admin.site.register(Collection, TranslatedAdmin)
admin.site.register(Stone, TranslatedAdmin)
admin.site.register(Material, TranslatedAdmin)


class PieceImageInline(TranslationTabularInline[PieceImage, Piece], TabularInline):  # type: ignore[misc]  # Unfold is untyped.
    ordering_field = "position"
    hide_ordering_field = True
    tab = False
    verbose_name = _("Foto")
    verbose_name_plural = _("Fotos")
    template = "admin/catalog/photo_grid.html"
    template_before = "admin/catalog/new_photos.html"
    model = PieceImage
    form: Any = PieceImageForm
    formset = PieceImageFormSet
    extra = 0
    fields = (
        "preview",
        "original",
        "alt",
        "position",
        "is_primary",
        "is_hover",
        "image_status",
    )
    readonly_fields = ("preview", "image_status")
    ordering = ("position",)

    @admin.display(description=_("Vista previa"))
    def preview(self, obj: PieceImage) -> str:
        paths = obj.renditions.get("webp", {}) if obj.processing_status == "ready" else {}
        src = (
            default_storage.url(paths[min(paths, key=int)])
            if paths
            else (obj.original.url if obj.original else None)
        )
        if not obj.pk and not src:
            return "—"
        preview = (
            format_html(
                '<img src="{}" alt="{}" style="width:64px;height:80px;object-fit:contain">',
                src,
                obj.alt,
            )
            if src
            else "—"
        )
        return format_html('<span data-photo-preview="{}">{}</span>', obj.pk or "", preview)

    @admin.display(description=_("Estado"))
    def image_status(self, obj: PieceImage) -> str:
        retry = (
            format_html(
                '<button type="submit" formmethod="post" formaction="{}" formnovalidate '
                'data-photo-retry="{}">Reintentar</button>',
                reverse("admin:catalog_piece_photo_retry", args=[obj.piece_id, obj.pk]),
                obj.pk,
            )
            if obj.pk and obj.processing_status == "failed"
            else ""
        )
        return format_html(
            '<span data-photo-id="{}" data-photo-status="{}" aria-live="polite">{}{}</span>',
            obj.pk or "",
            obj.processing_status,
            _("No se pudo procesar")
            if obj.processing_status == "failed"
            else ClientPresentationMixin.image_status(self, obj),
            retry,
        )


class PieceVideoInline(TranslationTabularInline[PieceVideo, Piece], TabularInline):  # type: ignore[misc]  # Unfold is untyped.
    tab = False
    verbose_name = _("Video")
    verbose_name_plural = _("Video")
    model = PieceVideo
    form: Any = PieceVideoForm
    max_num = 1
    extra = 0
    fields = ("original", "alt", "preview", "image_status")
    readonly_fields = ("preview", "image_status")
    image_status = ClientPresentationMixin.image_status

    @admin.display(description=_("Póster"))
    def preview(self, obj: PieceVideo) -> str:
        return (
            format_html('<img src="{}" width="128" alt="{}">', obj.poster.url, obj.alt)
            if obj.poster
            else "—"
        )


class CollectionPieceInline(TabularInline):  # type: ignore[misc]  # Unfold is untyped.
    ordering_field = "position"
    hide_ordering_field = True
    tab = False
    verbose_name = _("Colección")
    verbose_name_plural = _("Colecciones")
    model = CollectionPiece
    extra = 0


class CatalogHealthFilter(admin.SimpleListFilter):
    title = _("Salud del catálogo")
    parameter_name = "health"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:
        return [
            ("missing_en", str(_("Sin traducción inglesa"))),
            ("failed_images", str(_("Imágenes con errores"))),
        ]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Piece]) -> QuerySet[Piece]:
        if self.value() == "missing_en":
            return queryset.filter(missing_english_translation())
        if self.value() == "failed_images":
            return queryset.filter(images__processing_status="failed").distinct()
        return queryset


@admin.register(Piece)
class PieceAdmin(
    OptionalSelectionMixin,
    CatalogAuditHistoryMixin,
    ClientPresentationMixin,
    TranslationAdmin[Piece],
    ModelAdmin,  # type: ignore[misc]  # Unfold has no stubs.
):
    prepopulated_fields = {"slug": ("name",)}
    ordering_field = None
    hide_ordering_field = False
    form = PieceForm
    list_per_page = 25
    change_list_template = "admin/catalog/piece/change_list.html"
    change_form_template = "admin/catalog/piece/change_form.html"
    search_help_text = "Buscar por nombre o referencia"
    list_display = (
        "thumbnail",
        "piece_name",
        "category_path",
        "formatted_price",
        "editorial_badge",
        "sale_badge",
    )
    list_display_links = ("piece_name",)
    list_filter = (
        "status",
        "sale_state",
        "category",
        "stones",
        "collections",
        "is_new",
        CatalogHealthFilter,
    )
    search_fields = ("sku", "name_es", "name_en")
    readonly_fields = ("status", "sale_state", "published_at", "sold_at")
    filter_horizontal = ("stones", "materials")
    fieldsets = (
        (
            _("Información"),
            {
                "fields": (
                    "name",
                    "sku",
                    "short_description",
                    "long_description",
                    "story",
                    "care",
                ),
            },
        ),
        (
            _("Clasificación"),
            {
                # `related` is a form-only field (custom through model); added in get_fieldsets.
                "fields": ("category", "stones", "materials", "is_new"),
            },
        ),
        (
            _("Detalles de la pieza"),
            {
                "fields": (
                    "metal",
                    "metal_purity",
                    "ring_size",
                    "length_mm",
                    "dimensions_mm",
                    "weight_g",
                    "carats",
                )
            },
        ),
        (
            _("Precio y disponibilidad"),
            {
                "fields": ("price_cents", "sale_price_cents", "status", "sale_state"),
                "description": _(
                    "Usa los botones de esta página para publicar, ocultar, archivar "
                    "o cambiar la preventa."
                ),
            },
        ),
        (
            _("Buscadores (SEO)"),
            {
                "classes": ["collapse"],
                "fields": ("seo_title", "seo_description"),
                "description": _("Opcional. Cómo aparece la pieza en Google."),
            },
        ),
        (
            _("Avanzado"),
            {
                # Django expands collapsed fieldsets that contain errors.
                "classes": ["collapse"],
                "fields": (
                    "slug",
                    "piece_number",
                    "published_at",
                    "sold_at",
                    "position",
                ),
            },
        ),
    )
    inlines = (PieceImageInline, PieceVideoInline, CollectionPieceInline)
    actions = ("publish", "hide", "unhide", "archive", "preorder_on", "preorder_off", "duplicate")

    actions_detail = (
        "detail_publish",
        "detail_hide",
        "detail_unhide",
        "detail_preorder_on",
        "detail_preorder_off",
        "detail_release_cancelled",
        "detail_archive",
        "detail_duplicate",
    )
    delete_confirmation_template = "admin/catalog/delete_confirmation.html"
    actions_submit_line = ()
    change_form_before_template = "admin/catalog/piece_status.html"

    class Media:
        css = {"all": ("catalog/catalog-admin.css", "core/selection.css")}
        js = ("catalog/photo-status.js", "catalog/catalog-admin.js", "core/selection.js")

    def get_list_display(self, request: HttpRequest) -> Any:
        @admin.display(description="Acciones")
        def row_actions(obj: Piece) -> str:
            links = [
                (reverse("admin:catalog_piece_change", args=[obj.pk]), "Editar", "edit", False)
            ]
            if obj.status == Piece.Status.PUBLISHED:
                links.append((piece_url(obj, "es"), "Ver en la tienda", "open_in_new", True))
            if self.has_commercial_permission(request, obj):
                operations = []
                if self.has_duplicate_permission(request):
                    operations.append(("duplicate", "Duplicar", "content_copy"))
                if Piece.Status.PUBLISHED in services.EDITORIAL_TRANSITIONS[obj.status]:
                    operations.append(
                        ("unhide" if obj.status == "hidden" else "publish", "Publicar", "publish")
                    )
                if Piece.Status.HIDDEN in services.EDITORIAL_TRANSITIONS[obj.status]:
                    operations.append(("hide", "Ocultar", "visibility_off"))
                for operation, label, icon in operations:
                    links.append(
                        (
                            reverse(f"admin:catalog_piece_detail_{operation}", args=[obj.pk]),
                            label,
                            icon,
                            False,
                        )
                    )
            # Destructive action last, away from "Editar", to avoid accidental clicks.
            return format_html(
                '<div class="ca-actions">{}{}</div>',
                format_html_join(
                    "",
                    '<a class="ca-icon" href="{}" aria-label="{}" title="{}" {}>'
                    '<span class="material-symbols-outlined" aria-hidden="true">{}</span></a>',
                    (
                        (
                            url,
                            label,
                            label,
                            format_html('target="{}" rel="noopener"', "_blank") if external else "",
                            icon,
                        )
                        for url, label, icon, external in links
                    ),
                ),
                deletion_icon(obj, ", ".join(services.deletion_reasons(obj)), "Eliminar pieza")
                if self.has_delete_permission(request)
                else "",
            )

        return (*self.list_display, row_actions)

    @admin.display(description="Nombre", ordering="name_es")
    def piece_name(self, obj: Piece) -> str:
        return format_html(
            '<strong>{}</strong><small class="ca-sku">{}</small>', obj.name_es, obj.sku
        )

    @admin.display(description="Categoría", ordering="category__name_es")
    def category_path(self, obj: Piece) -> str:
        category = obj.category
        if not category:
            return "—"
        return (
            f"{cast(Category, category.parent).name} → {category.name}"
            if category.parent_id
            else str(category.name)
        )

    @admin.display(description="Estado editorial", ordering="status")
    def editorial_badge(self, obj: Piece) -> str:
        return format_html(
            '<span class="ca-badge" data-state="{}">{}</span>', obj.status, obj.get_status_display()
        )

    @admin.display(description="Estado de venta", ordering="sale_state")
    def sale_badge(self, obj: Piece) -> str:
        return format_html(
            '<span class="ca-badge" data-state="{}">{}</span>',
            obj.sale_state,
            obj.get_sale_state_display(),
        )

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:
        response = super().changelist_view(request, extra_context)
        if hasattr(response, "context_data") and "cl" in response.context_data:
            cl = response.context_data["cl"]
            count_list = copy(cl)
            count_list.filter_params = {
                k: v for k, v in cl.filter_params.items() if not k.startswith("status__")
            }
            counts = dict(
                count_list.get_queryset(request)
                .order_by()
                .values("status")
                .annotate(total=Count("pk", distinct=True))
                .values_list("status", "total")
            )
            tabs = []
            for value, label in [
                ("", "Todas"),
                ("draft", "Borradores"),
                ("published", "Publicadas"),
                ("hidden", "Ocultas"),
                ("archived", "Archivadas"),
            ]:
                query = request.GET.copy()
                query.pop("p", None)
                query.pop("status__exact", None)
                if value:
                    query["status__exact"] = value
                tabs.append(
                    {
                        "label": label,
                        "count": counts.get(value, 0) if value else sum(counts.values()),
                        "active": request.GET.get("status__exact", "") == value,
                        "url": "?" + query.urlencode(),
                    }
                )
            response.context_data.update(
                piece_tabs=tabs, catalog_has_pieces=Piece.objects.exists(), title="Piezas"
            )
        return response

    def render_change_form(
        self,
        request: HttpRequest,
        context: Any,
        add: bool = False,
        change: bool = False,
        form_url: str = "",
        obj: Any = None,
    ) -> Any:
        context["lost_new_photos"] = bool(request.FILES.getlist("new_photos"))
        piece = context["adminform"].form.instance
        missing = services.publication_missing(piece)
        checks = [
            ("Nombre", "nombre en español"),
            ("Categoría", "categoría"),
            ("Descripción corta", "descripción corta en español"),
            ("Precio", "precio"),
            ("Dirección en la web", "dirección web en español"),
        ]
        checklist = [
            {"label": label, "missing_key": key, "ready": key not in missing}
            for label, key in checks
        ]
        photo_missing = any("imagen" in key or "foto" in key for key in missing)
        checklist.append(
            {
                "label": "Foto principal",
                "photo": True,
                "ready": not photo_missing,
                "pending": any("procesando" in key for key in missing),
            }
        )
        can_publish = (
            self.has_commercial_permission(request, obj)
            and Piece.Status.PUBLISHED in services.EDITORIAL_TRANSITIONS[piece.status]
        )
        context.update(
            can_add_category=request.user.has_perm("catalog.add_category"),
            category_roots=Category.objects.filter(parent=None, is_active=True),
            publication_checklist=checklist,
            publication_missing=missing,
            can_publish=can_publish,
            publication_ready=not missing,
            catalog_editorial_badge=self.editorial_badge(piece),
            catalog_sale_badge=self.sale_badge(piece),
        )
        return super().render_change_form(request, context, add, change, form_url, obj)

    def get_urls(self) -> Any:
        return [
            path(
                "<path:object_id>/photos/status/",
                self.admin_site.admin_view(self.photo_status),
                name="catalog_piece_photo_status",
            ),
            path(
                "<path:object_id>/photos/<int:image_id>/retry/",
                self.admin_site.admin_view(self.photo_retry),
                name="catalog_piece_photo_retry",
            ),
            *super().get_urls(),
        ]

    def photo_piece(self, request: HttpRequest, object_id: str, *, change: bool = False) -> Piece:
        piece = get_object_or_404(self.get_queryset(request), pk=object_id)
        allowed = (
            self.has_change_permission(request, piece)
            if change
            else (
                request.user.has_perm("catalog.view_piece")
                and self.has_view_permission(request, piece)
            )
        )
        if not allowed:
            raise PermissionDenied
        return piece

    @method_decorator(require_GET)
    def photo_status(self, request: HttpRequest, object_id: str) -> JsonResponse:
        piece = self.photo_piece(request, object_id)
        photos = []
        for image in piece.images.all():
            paths = image.renditions.get("webp", {}) if image.processing_status == "ready" else {}
            photos.append(
                {
                    "id": image.pk,
                    "status": image.processing_status,
                    "thumb_url": default_storage.url(paths[min(paths, key=int)]) if paths else None,
                    "is_primary": image.is_primary,
                    "is_hover": image.is_hover,
                    "message": strip_tags(
                        str(ClientPresentationMixin.image_status(self, image))
                    ).strip(),
                }
            )
        missing = services.publication_missing(piece)
        return JsonResponse({"photos": photos, "ready_to_publish": not missing, "missing": missing})

    @method_decorator(require_POST)
    def photo_retry(self, request: HttpRequest, object_id: str, image_id: int) -> HttpResponse:
        piece = self.photo_piece(request, object_id, change=True)
        services.retry_piece_image(piece, image_id)
        if request.headers.get("Accept") == "application/json":
            return JsonResponse({"status": "pending"})
        self.message_user(request, "Se solicitó volver a procesar la foto.")
        return HttpResponseRedirect(reverse("admin:catalog_piece_change", args=[piece.pk]))

    def has_commercial_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        # Django combines action permissions with OR: this method deliberately requires both.
        return bool(
            self.has_change_permission(request, obj)
            and request.user.has_perm("catalog.publish_piece")
        )

    def get_actions(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
        actions: Any = super().get_actions(request)
        if not self.has_commercial_permission(request):
            for name in self.actions:
                actions.pop(name, None)
        if "delete_selected" in actions:
            actions["delete_selected"] = (
                type(self).delete_selected_checked,
                "delete_selected",
                actions["delete_selected"][2],
            )
        return actions

    @admin.action(permissions=["delete", "commercial", "change"])
    def delete_selected_checked(self, request: HttpRequest, queryset: QuerySet[Piece]) -> Any:
        if not self.has_delete_permission(request):
            raise PermissionDenied
        with transaction.atomic():
            pieces = list(queryset.order_by("pk").select_for_update(of=("self",)))
            failures = [
                f"{p.sku} ({', '.join(reasons)})"
                for p in pieces
                if (reasons := services.deletion_reasons(p))
            ]
            if failures:
                self.message_user(
                    request, "No se borró ninguna pieza: " + "; ".join(failures), messages.ERROR
                )
                return None
            return delete_selected(self, request, queryset)

    def changeform_view(
        self,
        request: HttpRequest,
        object_id: Any = None,
        form_url: str = "",
        extra_context: Any = None,
    ) -> HttpResponse:
        if "catalog_piece_save_publish" in request.POST and not self.has_commercial_permission(
            request
        ):
            raise PermissionDenied
        try:
            with transaction.atomic():
                return super().changeform_view(request, object_id, form_url, extra_context)
        except (ValidationError, DomainError) as exc:
            # Roll back all model/inline writes before rendering the same bound form.
            setattr(request, "_catalog_form_error", exc)  # noqa: B010 -- request attribute is dynamic.
            for uploads in request.FILES.lists():
                for upload in uploads[1]:
                    upload.seek(0)
            return super().changeform_view(request, object_id, form_url, extra_context)

    def get_form(
        self, request: HttpRequest, obj: Any = None, change: bool = False, **kwargs: Any
    ) -> Any:
        base = super().get_form(request, obj, change=change, **kwargs)
        error = getattr(request, "_catalog_form_error", None)
        if error is None:
            return base

        class ServiceErrorForm(base):  # type: ignore[valid-type, misc]  # Runtime-generated form subclass.
            def clean(self) -> Any:
                cleaned = super().clean()
                if isinstance(error, ValidationError) and hasattr(error, "error_dict"):
                    for field, errors in error.error_dict.items():
                        self.add_error(field if field in self.fields else None, errors)
                else:
                    self.add_error(
                        None,
                        "; ".join(error.messages)
                        if isinstance(error, ValidationError)
                        else str(error),
                    )
                return cleaned

        return ServiceErrorForm

    def copy_response(self, request: HttpRequest, copy: Piece) -> HttpResponseRedirect:
        self.message_user(
            request,
            f"Se creó una copia: «{copy.name_es}» (SKU {copy.sku}). "
            "Las fotos no se copian: agrégalas antes de publicar.",
            messages.SUCCESS,
        )
        return HttpResponseRedirect(reverse("admin:catalog_piece_change", args=[copy.pk]))

    def get_actions_detail(self, request: HttpRequest, object_id: int | str) -> Any:
        actions = super().get_actions_detail(request, object_id)
        piece = self.get_object(request, str(object_id))
        if piece and piece.status == "hidden":
            return [item for item in actions if item.action_name != "catalog_piece_detail_publish"]
        return actions

    def _has_active_reservation(self, request: HttpRequest, piece: Piece) -> bool:
        if request.method != "GET":
            return piece.reservations.filter(status="active").exists()
        cache = request.__dict__.setdefault("_catalog_active_reservations", {})
        if piece.pk not in cache:
            cache[piece.pk] = piece.reservations.filter(status="active").exists()
        return cast(bool, cache[piece.pk])

    def detail_allowed(self, request: HttpRequest, object_id: Any, operation: str) -> bool:
        piece = self.get_object(request, str(object_id)) if object_id else None
        if not piece or not self.has_commercial_permission(request, piece):
            return False
        if operation == "duplicate":
            return bool(self.has_duplicate_permission(request))
        return bool(
            {
                "publish": Piece.Status.PUBLISHED in services.EDITORIAL_TRANSITIONS[piece.status],
                "hide": Piece.Status.HIDDEN in services.EDITORIAL_TRANSITIONS[piece.status],
                "unhide": piece.status == "hidden",
                "archive": Piece.Status.ARCHIVED in services.EDITORIAL_TRANSITIONS[piece.status],
                "preorder_on": piece.status != "archived" and piece.sale_state == "available",
                "preorder_off": piece.status != "archived" and piece.sale_state == "preorder",
                "release_cancelled": piece.sale_state == "reserved"
                and not self._has_active_reservation(request, piece)
                and piece.status_changes.filter(from_state="sold", to_state="reserved").exists(),
            }.get(operation, False)
        )

    def piece_detail_action(
        self, request: HttpRequest, object_id: str, operation: str
    ) -> HttpResponse:
        if not self.detail_allowed(request, object_id, operation):
            raise PermissionDenied
        piece = self.get_object(request, object_id)
        if piece is None:
            raise PermissionDenied
        if request.method != "POST":
            return TemplateResponse(
                request,
                "admin/catalog/confirm_action.html",
                {
                    **self.admin_site.each_context(request),
                    "original": piece,
                    "title": {
                        "publish": _("Publicar"),
                        "hide": _("Ocultar"),
                        "unhide": _("Volver a publicar"),
                        "archive": _("Archivar"),
                        "duplicate": _("Duplicar"),
                        "preorder_on": _("Marcar preventa"),
                        "preorder_off": _("Quitar preventa"),
                        "release_cancelled": _("Volver a poner a la venta"),
                    }[operation],
                    "consequence": {
                        "publish": "Se verá en la tienda si cumple los requisitos de publicación.",
                        "hide": "Dejará de verse en la tienda; podrás volver a publicarla.",
                        "unhide": "Volverá a verse en la tienda si cumple los requisitos.",
                        "archive": "Dejará de verse en la tienda y no podrá volver a publicarse.",
                        "duplicate": "Se creará un borrador con otro SKU. Las fotos no se copian.",
                        "preorder_on": "Se ofrecerá en preventa.",
                        "preorder_off": "Dejará de ofrecerse en preventa.",
                        "release_cancelled": (
                            "La pieza retenida por cancelación "
                            "volverá a estar disponible para comprar."
                        ),
                    }[operation],
                    "back_url": reverse("admin:catalog_piece_change", args=[object_id]),
                },
            )
        try:
            if operation == "duplicate":
                return self.copy_response(
                    request, services.duplicate_piece(piece, request.user, request)
                )
            elif operation == "hide":
                services.hide_pieces(Piece.objects.filter(pk=piece.pk), request.user, request)
            elif operation == "release_cancelled":
                from apps.inventory.services import decide_cancelled_piece

                decide_cancelled_piece(piece.pk, actor=request.user, release=True)
            elif operation.startswith("preorder_"):
                set_preorder(piece, operation == "preorder_on", request.user)
            else:
                {
                    "publish": services.publish_piece,
                    "unhide": services.unhide,
                    "archive": services.archive_piece,
                }[operation](piece, request.user, request)
            self.message_user(request, _("Acción completada."), messages.SUCCESS)
        except (DomainError, ValidationError) as exc:
            self.message_user(request, str(exc), messages.ERROR)
        return HttpResponseRedirect(reverse("admin:catalog_piece_change", args=[object_id]))

    def has_detail_release_cancelled_permission(self, request, object_id=None):
        return self.detail_allowed(request, object_id, "release_cancelled")

    @action(description=_("Volver a poner a la venta"), permissions=["detail_release_cancelled"])
    def detail_release_cancelled(self, request, object_id):
        return self.piece_detail_action(request, object_id, "release_cancelled")

    @action(description=_("Guardar y publicar"), permissions=["commercial"])  # type: ignore[untyped-decorator]
    def save_publish(self, request: HttpRequest, obj: Piece) -> None:
        if not self.has_commercial_permission(request, obj):
            raise PermissionDenied
        # Called after related images are saved, so publication sees the complete piece.
        try:
            services.publish_piece(obj, request.user, request)
            self.message_user(request, _("Pieza publicada."), messages.SUCCESS)
        except (DomainError, ValidationError) as exc:
            obj.refresh_from_db()
            if (
                obj.status == Piece.Status.DRAFT
                and obj.images.filter(
                    is_primary=True, processing_status=PieceImage.ProcessingStatus.PENDING
                ).exists()
            ):
                self.message_user(
                    request,
                    "Se guardó como borrador. Las fotos se están procesando; "
                    "podrás publicar en unos segundos.",
                    messages.WARNING,
                )
            else:
                self.message_user(request, str(exc), messages.ERROR)

    def message_user(
        self,
        request: HttpRequest,
        message: Any,
        level: Any = messages.INFO,
        extra_tags: str = "",
        fail_silently: bool = False,
    ) -> None:
        from django.utils.safestring import SafeData, mark_safe

        if isinstance(message, SafeData) and "El pieza “" in str(message):
            message = cast(Any, message).replace("El pieza “", "La pieza “")
            message = message.replace("fue agregado correctamente", "se agregó correctamente")
            message = message.replace("se cambió correctamente", "se guardó correctamente")
            # Django constructs these messages with format_html; preserve its escaped markup.
            message = mark_safe(message)  # noqa: S308 -- Django already escaped the formatted message
        super().message_user(request, message, level, extra_tags, fail_silently)

    def response_add(
        self, request: HttpRequest, obj: Piece, post_url_continue: Any = None
    ) -> HttpResponse:
        if "catalog_piece_save_publish" in request.POST:
            self.save_publish(request, obj)
            return HttpResponseRedirect(reverse("admin:catalog_piece_change", args=[obj.pk]))
        return super().response_add(request, obj, post_url_continue)

    def response_change(self, request: HttpRequest, obj: Piece) -> HttpResponse:
        if "catalog_piece_save_publish" in request.POST:
            if not self.has_commercial_permission(request, obj):
                raise PermissionDenied
            self.save_publish(request, obj)
            return HttpResponseRedirect(reverse("admin:catalog_piece_change", args=[obj.pk]))
        return super().response_change(request, obj)

    def has_detail_publish_permission(self, request: HttpRequest, object_id: Any = None) -> bool:
        # Row actions are filtered per object by the row template and checked again here.
        if object_id is None:
            return bool(self.has_commercial_permission(request))
        return self.detail_allowed(request, object_id, "publish")

    @action(description=_("Publicar"), permissions=["detail_publish"])  # type: ignore[untyped-decorator]
    def detail_publish(self, request: HttpRequest, object_id: str) -> HttpResponse:
        return self.piece_detail_action(request, object_id, "publish")

    def has_detail_hide_permission(self, request: HttpRequest, object_id: Any = None) -> bool:
        # Row actions are filtered per object by the row template and checked again here.
        if object_id is None:
            return bool(self.has_commercial_permission(request))
        return self.detail_allowed(request, object_id, "hide")

    @action(description=_("Ocultar"), permissions=["detail_hide"])  # type: ignore[untyped-decorator]
    def detail_hide(self, request: HttpRequest, object_id: str) -> HttpResponse:
        return self.piece_detail_action(request, object_id, "hide")

    def has_detail_unhide_permission(self, request: HttpRequest, object_id: Any = None) -> bool:
        # Row actions are filtered per object by the row template and checked again here.
        if object_id is None:
            return bool(self.has_commercial_permission(request))
        return self.detail_allowed(request, object_id, "unhide")

    @action(description=_("Volver a publicar"), permissions=["detail_unhide"])  # type: ignore[untyped-decorator]
    def detail_unhide(self, request: HttpRequest, object_id: str) -> HttpResponse:
        return self.piece_detail_action(request, object_id, "unhide")

    def has_detail_preorder_on_permission(
        self, request: HttpRequest, object_id: Any = None
    ) -> bool:
        # Row actions are filtered per object by the row template and checked again here.
        if object_id is None:
            return bool(self.has_commercial_permission(request))
        return self.detail_allowed(request, object_id, "preorder_on")

    @action(description=_("Marcar preventa"), permissions=["detail_preorder_on"])  # type: ignore[untyped-decorator]
    def detail_preorder_on(self, request: HttpRequest, object_id: str) -> HttpResponse:
        return self.piece_detail_action(request, object_id, "preorder_on")

    def has_detail_preorder_off_permission(
        self, request: HttpRequest, object_id: Any = None
    ) -> bool:
        # Row actions are filtered per object by the row template and checked again here.
        if object_id is None:
            return bool(self.has_commercial_permission(request))
        return self.detail_allowed(request, object_id, "preorder_off")

    @action(description=_("Quitar preventa"), permissions=["detail_preorder_off"])  # type: ignore[untyped-decorator]
    def detail_preorder_off(self, request: HttpRequest, object_id: str) -> HttpResponse:
        return self.piece_detail_action(request, object_id, "preorder_off")

    def has_detail_archive_permission(self, request: HttpRequest, object_id: Any = None) -> bool:
        # Row actions are filtered per object by the row template and checked again here.
        if object_id is None:
            return bool(self.has_commercial_permission(request))
        return self.detail_allowed(request, object_id, "archive")

    @action(description=_("Archivar"), permissions=["detail_archive"])  # type: ignore[untyped-decorator]
    def detail_archive(self, request: HttpRequest, object_id: str) -> HttpResponse:
        return self.piece_detail_action(request, object_id, "archive")

    def has_detail_duplicate_permission(self, request: HttpRequest, object_id: Any = None) -> bool:
        # Row actions are filtered per object by the row template and checked again here.
        if object_id is None:
            return bool(self.has_commercial_permission(request))
        return self.detail_allowed(request, object_id, "duplicate")

    @action(description=_("Duplicar"), permissions=["detail_duplicate"])  # type: ignore[untyped-decorator]
    def detail_duplicate(self, request: HttpRequest, object_id: str) -> HttpResponse:
        return self.piece_detail_action(request, object_id, "duplicate")

    def has_duplicate_permission(self, request: HttpRequest) -> bool:
        return self.has_commercial_permission(request) and request.user.has_perm(
            "catalog.add_piece"
        )

    @admin.action(description=_("Duplicar como nueva pieza"), permissions=["duplicate"])
    def duplicate(
        self, request: HttpRequest, queryset: QuerySet[Piece]
    ) -> HttpResponseRedirect | None:
        if not self.has_duplicate_permission(request):
            raise PermissionDenied
        if queryset.count() != 1:
            self.message_user(
                request, "Selecciona una sola pieza para duplicar y abrir su copia.", messages.ERROR
            )
            return None
        return self.copy_response(
            request, services.duplicate_piece(queryset.get(), request.user, request)
        )

    def get_object(self, request, object_id, from_field=None):
        # Unfold asks once per detail action. Share reads only inside this GET request;
        # POST operations always re-read and services acquire their own row locks.
        if request.method != "GET":
            return super().get_object(request, object_id, from_field)
        cache = getattr(request, "_catalog_piece_objects", None)
        if cache is None:
            cache = request._catalog_piece_objects = {}
        key = (str(object_id), from_field)
        if key not in cache:
            cache[key] = super().get_object(request, object_id, from_field)
        return cache[key]

    def get_queryset(self, request: HttpRequest) -> QuerySet[Piece]:
        queryset = Piece.objects.select_related("category__parent")
        if request.resolver_match and request.resolver_match.url_name == "catalog_piece_changelist":
            return queryset.annotate(
                deletion_reservations=Exists(
                    Piece.objects.filter(pk=OuterRef("pk"), reservations__isnull=False)
                ),
                deletion_status_changes=Exists(
                    Piece.objects.filter(pk=OuterRef("pk"), status_changes__isnull=False)
                ),
                deletion_orderitem_set=Exists(
                    Piece.objects.filter(pk=OuterRef("pk"), orderitem__isnull=False)
                ),
            ).prefetch_related(
                Prefetch(
                    "images",
                    queryset=PieceImage.objects.filter(is_primary=True),
                    to_attr="list_primary_images",
                )
            )
        return queryset.prefetch_related("images")

    def get_readonly_fields(
        self, request: HttpRequest, obj: Piece | None = None
    ) -> tuple[str, ...]:
        fields: tuple[str, ...] = self.readonly_fields
        if not request.user.has_perm("catalog.change_piece_price"):
            fields += ("price_cents", "sale_price_cents", "regular_price_cop", "sale_price_cop")
        return fields

    def get_fieldsets(self, request: HttpRequest, obj: Piece | None = None) -> Any:
        fieldsets = [
            (title, {**options, "fields": [*options["fields"], "related"]})
            if "is_new" in options["fields"]
            else (title, options)
            for title, options in super().get_fieldsets(request, obj)
        ]
        english = []
        translated = []
        for title, options in fieldsets:
            fields = []
            for field in options["fields"]:
                if isinstance(field, str) and field.endswith("_en"):
                    english.append(field)
                else:
                    fields.append(field)
            translated.append((title, {**options, "fields": fields}))
        if english:
            translated.insert(
                4, (_("Inglés (opcional)"), {"classes": ["collapse"], "fields": english})
            )
        fieldsets = translated
        if request.user.has_perm("catalog.change_piece_price"):
            return fieldsets
        replacements = {"price_cents": "regular_price_cop", "sale_price_cents": "sale_price_cop"}
        return [
            (
                title,
                {
                    **options,
                    "fields": list(
                        dict.fromkeys(replacements.get(f, f) for f in options["fields"])
                    ),
                },
            )
            for title, options in fieldsets
        ]

    @admin.display(description=_("Precio (COP)"))
    def regular_price_cop(self, obj: Piece) -> str:
        return format_admin_cop(obj.price_cents) if obj.price_cents is not None else "—"

    @admin.display(description=_("Precio rebajado (COP)"))
    def sale_price_cop(self, obj: Piece) -> str:
        return format_admin_cop(obj.sale_price_cents) if obj.sale_price_cents is not None else "—"

    def get_prepopulated_fields(
        self, request: HttpRequest, obj: Piece | None = None
    ) -> dict[str, Sequence[str]]:
        if obj and obj.published_at:
            return {}
        return dict(super().get_prepopulated_fields(request, obj))

    def save_model(self, request: HttpRequest, obj: Piece, form: Any, change: bool) -> None:
        try:
            services.save_piece(obj, actor=request.user, request=request)
        except PermissionDenied as exc:
            # The service retains its permission guard; authorized form edits show the reason.
            raise ValidationError(str(exc)) from exc

    def save_related(self, request: HttpRequest, form: Any, formsets: Any, change: bool) -> None:
        services.save_piece_relations(
            form.instance, form.cleaned_data, actor=request.user, request=request
        )
        for formset in formsets:
            self.save_formset(request, form, formset, change)
        photo_errors = services.append_piece_photos(
            form.instance, request.FILES.getlist("new_photos"), actor=request.user, request=request
        )
        for error in photo_errors:
            self.message_user(request, error, messages.ERROR)
        if photo_errors:
            self.message_user(
                request, "Vuelve a elegir las fotos que no se pudieron cargar.", messages.ERROR
            )

    def save_formset(self, request: HttpRequest, form: Any, formset: Any, change: bool) -> None:
        if formset.model is PieceImage:
            formset.save(commit=False)
            photos = [
                image_form.instance
                for image_form in formset.forms
                if image_form.cleaned_data and not image_form.cleaned_data.get("DELETE")
            ]
            services.apply_photo_changes(form.instance, photos, actor=request.user, request=request)
            formset.save_m2m()
            return
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            if isinstance(obj, PieceVideo):
                services.delete_catalog_object(obj, actor=request.user, request=request)
            elif isinstance(obj, PieceImage):
                services.delete_piece_image(obj)
            else:
                services.delete_catalog_object(obj, actor=request.user, request=request)
        for obj in instances:
            if isinstance(obj, PieceVideo):
                services.save_piece_video(obj)
            elif isinstance(obj, PieceImage):
                services.save_piece_image(obj)
            else:
                services.save_collection_piece(obj, actor=request.user, request=request)

    def has_delete_permission(self, request: HttpRequest, obj: Piece | None = None) -> bool:
        return (
            bool(super().has_delete_permission(request, obj))
            and self.has_commercial_permission(request, obj)
            and (obj is None or not services.deletion_reasons(obj))
        )

    def delete_model(self, request: HttpRequest, obj: Piece) -> None:
        services.delete_piece(obj, actor=request.user, request=request)

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[Piece]) -> None:
        if not self.has_delete_permission(request):
            raise PermissionDenied
        services.delete_pieces(queryset, actor=request.user, request=request)

    @admin.display(description=_("Imagen"))
    def thumbnail(self, obj: Piece) -> str:
        image = next(
            (
                image
                for image in (
                    obj.list_primary_images
                    if hasattr(obj, "list_primary_images")
                    else obj.images.all()
                )
                if image.is_primary and image.processing_status == "ready"
            ),
            None,
        )
        return (
            format_html(
                '<img class="ca-thumb" src="{}" width="48" height="48" loading="lazy" alt="">',
                thumbnail_url(image),
            )
            if image
            else "—"
        )

    @admin.display(description=_("Precio COP"))
    def formatted_price(self, obj: Piece) -> str:
        return format_admin_cop(obj.effective_price.amount_cents)

    def _action(self, request: HttpRequest, queryset: QuerySet[Piece], action: str) -> None:
        if not self.has_commercial_permission(request):
            raise PermissionDenied
        successes, failures = 0, []
        for piece in queryset:
            try:
                with transaction.atomic():
                    if action == "hide":
                        services.hide_pieces(
                            Piece.objects.filter(pk=piece.pk), request.user, request
                        )
                    elif action in ("preorder_on", "preorder_off"):
                        set_preorder(piece, action == "preorder_on", request.user)
                    else:
                        function = {
                            "publish": services.publish_piece,
                            "unhide": services.unhide,
                            "archive": services.archive_piece,
                        }[action]
                        function(piece, request.user, request)
            except (DomainError, ValidationError) as exc:
                reason = "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
                failures.append(f"{piece.sku} ({reason})")
            else:
                successes += 1
        label = {
            "publish": "publicadas",
            "unhide": "publicadas",
            "hide": "ocultadas",
            "archive": "archivadas",
            "preorder_on": "marcadas en preventa",
            "preorder_off": "retiradas de preventa",
        }[action]
        if successes == 1:
            message = f"1 pieza {label.replace('adas', 'ada')}."
        else:
            message = f"{successes} piezas {label}."
        if failures:
            verb = {
                "publish": "publicar",
                "unhide": "volver a publicar",
                "hide": "ocultar",
                "archive": "archivar",
                "preorder_on": "marcar en preventa",
                "preorder_off": "retirar de preventa",
            }[action]
            result = "no se pudo" if len(failures) == 1 else "no se pudieron"
            message += f" {len(failures)} {result} {verb}: " + "; ".join(failures)
        self.message_user(request, message, messages.WARNING if failures else messages.SUCCESS)

    @admin.action(description=_("Publicar"), permissions=["commercial", "change"])
    def publish(self, request: HttpRequest, queryset: QuerySet[Piece]) -> None:
        self._action(request, queryset, "publish")

    @admin.action(description=_("Ocultar del catálogo"), permissions=["commercial", "change"])
    def hide(self, request: HttpRequest, queryset: QuerySet[Piece]) -> None:
        self._action(request, queryset, "hide")

    @admin.action(description=_("Volver a publicar"), permissions=["commercial", "change"])
    def unhide(self, request: HttpRequest, queryset: QuerySet[Piece]) -> None:
        self._action(request, queryset, "unhide")

    @admin.action(description=_("Archivar"), permissions=["commercial", "change"])
    def archive(self, request: HttpRequest, queryset: QuerySet[Piece]) -> None:
        self._action(request, queryset, "archive")

    @admin.action(description=_("Marcar como preventa"), permissions=["commercial", "change"])
    def preorder_on(self, request: HttpRequest, queryset: QuerySet[Piece]) -> None:
        self._action(request, queryset, "preorder_on")

    @admin.action(description=_("Quitar preventa"), permissions=["commercial", "change"])
    def preorder_off(self, request: HttpRequest, queryset: QuerySet[Piece]) -> None:
        self._action(request, queryset, "preorder_off")


@admin.register(PieceImage)
class PieceImageAdmin(ClientPresentationMixin, TabbedTranslationAdmin[PieceImage], ModelAdmin):  # type: ignore[misc]  # Unfold is untyped.
    form: Any = PieceImageForm
    exclude = ("renditions", "width", "height", "processing_status", "error")
    readonly_fields = ("image_preview", "image_status")

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        try:
            with transaction.atomic():
                return super().changeform_view(request, object_id, form_url, extra_context)
        except ValidationError as exc:
            request._catalog_photo_error = exc
            return super().changeform_view(request, object_id, form_url, extra_context)

    def get_form(self, request, obj=None, change=False, **kwargs):
        base = super().get_form(request, obj, change=change, **kwargs)
        error = getattr(request, "_catalog_photo_error", None)
        if error is None:
            return base

        class PhotoErrorForm(base):  # type: ignore[valid-type, misc]  # Runtime-generated form subclass.
            def clean(self):
                cleaned = super().clean()
                self.add_error(None, error)
                return cleaned

        return PhotoErrorForm

    def delete_view(self, request, object_id, extra_context=None):
        try:
            return super().delete_view(request, object_id, extra_context)
        except ValidationError as exc:
            self.message_user(request, "; ".join(exc.messages), messages.ERROR)
            return HttpResponseRedirect(
                reverse("admin:catalog_pieceimage_change", args=[object_id])
            )

    def changelist_view(self, request, extra_context=None):
        try:
            with transaction.atomic():
                return super().changelist_view(request, extra_context)
        except ValidationError as exc:
            self.message_user(request, "; ".join(exc.messages), messages.ERROR)
            return HttpResponseRedirect(reverse("admin:catalog_pieceimage_changelist"))

    def save_model(self, request: HttpRequest, obj: PieceImage, form: Any, change: bool) -> None:
        previous = PieceImage.objects.filter(pk=obj.pk).first() if change else None
        if previous and previous.piece_id != obj.piece_id:
            raise ValidationError("No se puede mover una foto a otra pieza.")
        photos = [photo for photo in obj.piece.images.all() if photo.pk != obj.pk]
        services.apply_photo_changes(obj.piece, [*photos, obj], actor=request.user, request=request)

    def delete_model(self, request: HttpRequest, obj: PieceImage) -> None:
        services.apply_photo_changes(
            obj.piece,
            list(obj.piece.images.exclude(pk=obj.pk)),
            actor=request.user,
            request=request,
        )

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[PieceImage]) -> None:
        ids = list(queryset.values_list("pk", flat=True))
        for piece in Piece.objects.filter(images__pk__in=ids).distinct():
            services.apply_photo_changes(
                piece, list(piece.images.exclude(pk__in=ids)), actor=request.user, request=request
            )
