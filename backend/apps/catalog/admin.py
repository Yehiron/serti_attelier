from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from django.contrib import admin, messages
from django.contrib.admin.actions import delete_selected
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin, TranslationTabularInline
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action

from apps.core.admin_presentation import ClientPresentationMixin, thumbnail_url
from apps.core.exceptions import DomainError
from apps.core.formatting import format_admin_cop
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


class TranslatedAdmin(ClientPresentationMixin, TabbedTranslationAdmin[Any], ModelAdmin):  # type: ignore[misc]  # Unfold is untyped.
    prepopulated_fields = {"slug": ("name",)}
    search_fields: ClassVar[tuple[str, ...]] = ("name_es", "name_en")
    list_display: tuple[str, ...] = ("name", "position")
    form: Any = ValidatedImageForm
    ordering_field: str | None = "position"
    hide_ordering_field = True
    readonly_fields: ClassVar[tuple[str, ...]] = ("image_preview", "image_status")

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
    ordering_field = "position"
    hide_ordering_field = True
    tab = True
    verbose_name = _("Foto")
    verbose_name_plural = _("Fotos")
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
    image_status = ClientPresentationMixin.image_status
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
    tab = True
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
    tab = True
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
class PieceAdmin(TranslatedAdmin):
    ordering_field = None
    hide_ordering_field = False
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
                    "attributes",
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
        "detail_archive",
        "detail_duplicate",
    )
    actions_row = ("detail_publish",)
    actions_submit_line = ("save_publish",)
    change_form_before_template = "admin/catalog/piece_status.html"

    def has_commercial_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        # Django combines action permissions with OR: this method deliberately requires both.
        return bool(
            self.has_change_permission(request, obj)
            and request.user.has_perm("catalog.publish_piece")
        )

    def get_actions(self, request: HttpRequest) -> Any:
        actions = super().get_actions(request)
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
            request._catalog_form_error = exc
            for uploads in request.FILES.lists():
                for upload in uploads[1]:
                    upload.seek(0)
            return super().changeform_view(request, object_id, form_url, extra_context)

    def get_form(self, request: HttpRequest, obj: Any = None, **kwargs: Any) -> Any:
        base = super().get_form(request, obj, **kwargs)
        error = getattr(request, "_catalog_form_error", None)
        if error is None:
            return base

        class ServiceErrorForm(base):
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
                    }[operation],
                    "consequence": {
                        "publish": "Se verá en la tienda si cumple los requisitos de publicación.",
                        "hide": "Dejará de verse en la tienda; podrás volver a publicarla.",
                        "unhide": "Volverá a verse en la tienda si cumple los requisitos.",
                        "archive": "Dejará de verse en la tienda y no podrá volver a publicarse.",
                        "duplicate": "Se creará un borrador con otro SKU. Las fotos no se copian.",
                        "preorder_on": "Se ofrecerá en preventa.",
                        "preorder_off": "Dejará de ofrecerse en preventa.",
                    }[operation],
                    "back_url": reverse("admin:catalog_piece_change", args=[object_id]),
                },
            )
        try:
            if operation == "duplicate":
                return self.copy_response(request, services.duplicate_piece(piece, request.user))
            elif operation == "hide":
                services.hide_pieces(Piece.objects.filter(pk=piece.pk), request.user, request)
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
        return self.copy_response(request, services.duplicate_piece(queryset.get(), request.user))

    def get_queryset(self, request: HttpRequest) -> QuerySet[Piece]:
        return Piece.objects.select_related("category").prefetch_related("images")

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
        services.save_piece_relations(form.instance, form.cleaned_data)
        for formset in formsets:
            self.save_formset(request, form, formset, change)
        for error in services.append_piece_photos(
            form.instance, request.FILES.getlist("new_photos")
        ):
            self.message_user(request, error, messages.ERROR)

    def save_formset(self, request: HttpRequest, form: Any, formset: Any, change: bool) -> None:
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            if isinstance(obj, PieceVideo):
                services.delete_catalog_object(obj)
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
        return (
            bool(super().has_delete_permission(request, obj))
            and self.has_commercial_permission(request, obj)
            and (obj is None or not services.deletion_reasons(obj))
        )

    def delete_model(self, request: HttpRequest, obj: Piece) -> None:
        services.delete_piece(obj)

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[Piece]) -> None:
        if not self.has_delete_permission(request):
            raise PermissionDenied
        services.delete_pieces(queryset)

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
        return (
            format_html('<img src="{}" width="64" alt="">', thumbnail_url(image)) if image else "—"
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

    def save_model(self, request: HttpRequest, obj: PieceImage, form: Any, change: bool) -> None:
        services.save_piece_image(obj)

    def delete_model(self, request: HttpRequest, obj: PieceImage) -> None:
        services.delete_piece_image(obj)

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[PieceImage]) -> None:
        for obj in queryset:
            services.delete_piece_image(obj)
