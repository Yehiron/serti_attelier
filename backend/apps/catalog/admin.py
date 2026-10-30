from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin, TranslationTabularInline
from unfold.admin import ModelAdmin, TabularInline

from apps.core.exceptions import DomainError
from apps.inventory.services import set_preorder

from . import services
from .forms import PieceForm, PieceImageForm, PieceImageFormSet, PieceVideoForm, ValidatedImageForm
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


class TranslatedAdmin(TabbedTranslationAdmin[Any], ModelAdmin):  # type: ignore[misc]  # Unfold is untyped.
    prepopulated_fields = {"slug": ("name",)}
    search_fields: ClassVar[tuple[str, ...]] = ("name_es", "name_en")
    list_display: tuple[str, ...] = ("name", "position")
    form: Any = ValidatedImageForm

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:
        services.save_taxonomy(obj)

    def delete_model(self, request: HttpRequest, obj: Any) -> None:
        services.delete_catalog_object(obj)

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> None:
        for obj in queryset:
            services.delete_catalog_object(obj)


admin.site.register(Category, TranslatedAdmin)
admin.site.register(Collection, TranslatedAdmin)
admin.site.register(Stone, TranslatedAdmin)
admin.site.register(Material, TranslatedAdmin)


class PieceImageInline(TranslationTabularInline[PieceImage, Piece], TabularInline):  # type: ignore[misc]  # Unfold is untyped.
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
        "processing_status",
        "error",
    )
    readonly_fields = ("preview", "processing_status", "error")
    ordering = ("position",)

    @admin.display(description=_("Vista previa"))
    def preview(self, obj: PieceImage) -> str:
        paths = obj.renditions.get("webp", {}) if obj.processing_status == "ready" else {}
        src = (
            default_storage.url(paths[min(paths, key=int)])
            if paths
            else (obj.original.url if obj.original else None)
        )
        return (
            format_html(
                '<img src="{}" alt="{}" style="width:64px;height:80px;object-fit:contain">',
                src,
                obj.alt,
            )
            if src
            else "—"
        )


class PieceVideoInline(TranslationTabularInline[PieceVideo, Piece], TabularInline):  # type: ignore[misc]  # Unfold is untyped.
    model = PieceVideo
    form: Any = PieceVideoForm
    max_num = 1
    extra = 0
    fields = ("original", "alt", "preview", "processing_status", "duration_seconds", "error")
    readonly_fields = ("preview", "processing_status", "duration_seconds", "error")

    @admin.display(description=_("Póster"))
    def preview(self, obj: PieceVideo) -> str:
        return (
            format_html('<img src="{}" width="128" alt="{}">', obj.poster.url, obj.alt)
            if obj.poster
            else "—"
        )


class CollectionPieceInline(TabularInline):  # type: ignore[misc]  # Unfold is untyped.
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
class PieceAdmin(TranslatedAdmin):
    form = PieceForm
    list_display = (
        "thumbnail",
        "sku",
        "name",
        "category",
        "formatted_price",
        "sale_state",
        "status",
    )
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
    inlines = (PieceImageInline, PieceVideoInline, CollectionPieceInline)
    actions = ("publish", "hide", "unhide", "archive", "preorder_on", "preorder_off", "duplicate")

    def has_duplicate_permission(self, request: HttpRequest) -> bool:
        return request.user.has_perm("catalog.add_piece") and request.user.has_perm(
            "catalog.change_piece"
        )

    @admin.action(description=_("Duplicar como nueva pieza"), permissions=["duplicate"])
    def duplicate(
        self, request: HttpRequest, queryset: QuerySet[Piece]
    ) -> HttpResponseRedirect | None:
        copies = [services.duplicate_piece(piece, request.user) for piece in queryset]
        if len(copies) == 1:
            return HttpResponseRedirect(reverse("admin:catalog_piece_change", args=[copies[0].pk]))
        self.message_user(request, _("Piezas duplicadas como borradores."))
        return None

    def get_queryset(self, request: HttpRequest) -> QuerySet[Piece]:
        return Piece.objects.select_related("category").prefetch_related("images")

    def get_readonly_fields(
        self, request: HttpRequest, obj: Piece | None = None
    ) -> tuple[str, ...]:
        fields: tuple[str, ...] = self.readonly_fields
        if not request.user.has_perm("catalog.change_piece_price"):
            fields += ("price_cents", "sale_price_cents")
        return fields

    def get_prepopulated_fields(
        self, request: HttpRequest, obj: Piece | None = None
    ) -> dict[str, Sequence[str]]:
        if obj and obj.published_at:
            return {}
        return dict(super().get_prepopulated_fields(request, obj))

    def save_model(self, request: HttpRequest, obj: Piece, form: Any, change: bool) -> None:
        services.save_piece(obj, actor=request.user, request=request)

    def save_related(self, request: HttpRequest, form: Any, formsets: Any, change: bool) -> None:
        services.save_piece_relations(form.instance, form.cleaned_data)
        for formset in formsets:
            self.save_formset(request, form, formset, change)

    def save_formset(self, request: HttpRequest, form: Any, formset: Any, change: bool) -> None:
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            if isinstance(obj, PieceVideo):
                obj.delete()
            elif isinstance(obj, PieceImage):
                services.delete_piece_image(obj)
            else:
                services.delete_catalog_object(obj)
        for obj in instances:
            if isinstance(obj, PieceVideo):
                services.save_piece_video(obj)
            elif isinstance(obj, PieceImage):
                services.save_piece_image(obj)
            else:
                services.save_collection_piece(obj)

    def has_delete_permission(self, request: HttpRequest, obj: Piece | None = None) -> bool:
        return bool(super().has_delete_permission(request, obj)) and (
            obj is None or obj.status == "draft"
        )

    def delete_model(self, request: HttpRequest, obj: Piece) -> None:
        services.delete_piece(obj)

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[Piece]) -> None:
        for piece in queryset:
            services.delete_piece(piece)

    @admin.display(description=_("Imagen"))
    def thumbnail(self, obj: Piece) -> str:
        image = next(
            (
                image
                for image in obj.images.all()
                if image.is_primary and image.processing_status == "ready"
            ),
            None,
        )
        return format_html('<img src="{}" width="64" alt="">', image.original.url) if image else "—"

    @admin.display(description=_("Precio COP"))
    def formatted_price(self, obj: Piece) -> str:
        return f"$ {obj.effective_price.amount_cents // 100:,}".replace(",", ".")

    def _action(self, request: HttpRequest, queryset: QuerySet[Piece], action: str) -> None:
        for piece in queryset:
            try:
                if action == "hide":
                    services.hide_pieces(Piece.objects.filter(pk=piece.pk), request.user, request)
                elif action in ("preorder_on", "preorder_off", "duplicate"):
                    set_preorder(piece, action == "preorder_on", request.user)
                else:
                    function = {
                        "publish": services.publish_piece,
                        "unhide": services.unhide,
                        "archive": services.archive_piece,
                    }[action]
                    function(piece, request.user, request)
            except (DomainError, ValidationError) as exc:
                self.message_user(request, f"{piece}: {exc}", messages.ERROR)

    @admin.action(description=_("Publicar"))
    def publish(self, request: HttpRequest, queryset: QuerySet[Piece]) -> None:
        self._action(request, queryset, "publish")

    @admin.action(description=_("Ocultar del catálogo"))
    def hide(self, request: HttpRequest, queryset: QuerySet[Piece]) -> None:
        self._action(request, queryset, "hide")

    @admin.action(description=_("Volver a publicar"))
    def unhide(self, request: HttpRequest, queryset: QuerySet[Piece]) -> None:
        self._action(request, queryset, "unhide")

    @admin.action(description=_("Archivar"))
    def archive(self, request: HttpRequest, queryset: QuerySet[Piece]) -> None:
        self._action(request, queryset, "archive")

    @admin.action(description=_("Marcar como preventa"))
    def preorder_on(self, request: HttpRequest, queryset: QuerySet[Piece]) -> None:
        self._action(request, queryset, "preorder_on")

    @admin.action(description=_("Quitar preventa"))
    def preorder_off(self, request: HttpRequest, queryset: QuerySet[Piece]) -> None:
        self._action(request, queryset, "preorder_off")


@admin.register(PieceImage)
class PieceImageAdmin(TabbedTranslationAdmin[PieceImage], ModelAdmin):  # type: ignore[misc]  # Unfold is untyped.
    form: Any = PieceImageForm
    readonly_fields = ("renditions", "width", "height", "processing_status", "error")

    def save_model(self, request: HttpRequest, obj: PieceImage, form: Any, change: bool) -> None:
        services.save_piece_image(obj)

    def delete_model(self, request: HttpRequest, obj: PieceImage) -> None:
        services.delete_piece_image(obj)

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[PieceImage]) -> None:
        for obj in queryset:
            services.delete_piece_image(obj)
