from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin, TranslationTabularInline
from unfold.admin import ModelAdmin, TabularInline

from apps.core.exceptions import DomainError
from apps.inventory.services import set_preorder

from . import services
from .forms import PieceForm, ValidatedImageForm
from .models import Category, Collection, CollectionPiece, Material, Piece, PieceImage, Stone


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
    form: Any = ValidatedImageForm
    extra = 0
    fields = ("original", "alt", "position", "is_primary", "processing_status", "error")
    readonly_fields = ("processing_status", "error")
    ordering = ("position",)


class CollectionPieceInline(TabularInline):  # type: ignore[misc]  # Unfold is untyped.
    model = CollectionPiece
    extra = 0


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
    list_filter = ("status", "sale_state", "category", "stones", "collections", "is_new")
    search_fields = ("sku", "name_es", "name_en")
    readonly_fields = ("status", "sale_state", "published_at", "sold_at")
    inlines = (PieceImageInline, CollectionPieceInline)
    actions = ("publish", "hide", "unhide", "archive", "preorder_on", "preorder_off")

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
            if isinstance(obj, PieceImage):
                services.delete_piece_image(obj)
            else:
                services.delete_catalog_object(obj)
        for obj in instances:
            if isinstance(obj, PieceImage):
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
    form: Any = ValidatedImageForm
    readonly_fields = ("renditions", "width", "height", "processing_status", "error")

    def save_model(self, request: HttpRequest, obj: PieceImage, form: Any, change: bool) -> None:
        services.save_piece_image(obj)

    def delete_model(self, request: HttpRequest, obj: PieceImage) -> None:
        services.delete_piece_image(obj)

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[PieceImage]) -> None:
        for obj in queryset:
            services.delete_piece_image(obj)
