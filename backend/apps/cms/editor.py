"""Permission-scoped admin visual editor and CSRF-protected draft actions."""

from __future__ import annotations

import json
from typing import Any, cast

from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.catalog import services as catalog_services
from apps.catalog.models import Category, Collection, Piece, Stone

from . import editor_services, services
from .admin import HomeSectionAdmin
from .models import HeroSlide, HomeSection
from .selectors import draft_sections, home_categories

TAXONOMIES = {"category": Category, "stone": Stone, "collection": Collection}


def can_edit(request: HttpRequest) -> bool:
    return request.user.has_perm("cms.change_homesection") or request.user.has_perm(
        "catalog.change_category"
    )


def thumbnail(renditions: dict[str, Any]) -> str:
    paths = renditions.get("webp", {})
    return default_storage.url(paths[min(paths, key=int)]) if paths else ""


def taxonomy_cards(model: Any, request: HttpRequest) -> list[dict[str, Any]]:
    name = model._meta.model_name
    relation = {"category": "category", "stone": "stones", "collection": "collections"}[name]
    cards = []
    queryset = model.objects.annotate(
        published_total=Count(
            "pieces", filter=Q(pieces__status=Piece.Status.PUBLISHED), distinct=True
        )
    )
    if model is Category:
        queryset = queryset.prefetch_related("children")
    for obj in queryset:
        cards.append(
            {
                "id": obj.pk,
                "name": obj.name_es,
                "image": thumbnail(obj.cover_renditions),
                "count": obj.published_total,
                "children": list(obj.children.all()) if isinstance(obj, Category) else [],
                "edit": reverse(f"admin:catalog_{name}_change", args=[obj.pk]),
                "pieces": reverse("admin:catalog_piece_changelist")
                + f"?{relation}__id__exact={obj.pk}",
                "can_change": request.user.has_perm(f"catalog.change_{name}"),
            }
        )
    return cards


def editor(request: HttpRequest) -> HttpResponse:
    if not can_edit(request):
        raise PermissionDenied
    device = request.GET.get("device", "desktop")
    if device not in HeroSlide.Device.values:
        device = "desktop"
    sections = []
    for section in draft_sections():
        slides = [
            {"id": slide.pk, "image": thumbnail(slide.renditions), "alt": slide.alt_es}
            for slide in section.slides.all()
            if slide.device == device
        ]
        pieces = []
        if section.kind == "collection_rail" and section.collection:
            for piece in (
                section.collection.pieces.filter(status="published")
                .exclude(sale_state="sold")
                .order_by("collectionpiece__position", "collectionpiece__pk")
                .prefetch_related("images")[:6]
            ):
                photo = next(
                    (
                        image
                        for image in piece.images.all()
                        if image.is_primary and image.processing_status == "ready"
                    ),
                    None,
                )
                pieces.append(
                    {"name": piece.name_es, "image": thumbnail(photo.renditions) if photo else ""}
                )
        sections.append(
            {
                "obj": section,
                "image": thumbnail(section.renditions),
                "slides": slides,
                "pieces": pieces,
                "edit": reverse("admin:cms_homesection_change", args=[section.pk]),
            }
        )
    groups = []
    for name, label, note, add_label in [
        (
            "category",
            _("Categorías"),
            _(
                "La foto se ve en «Comprar por categoría» de la página de inicio. "
                "Usa una foto vertical."
            ),
            _("Nueva categoría"),
        ),
        (
            "stone",
            _("Piedras"),
            _("Se ve en las piedras de la página de inicio y en el catálogo"),
            _("Nueva piedra"),
        ),
        (
            "collection",
            _("Colecciones"),
            _("Se ve en el menú y en las colecciones de la página de inicio"),
            _("Nueva colección"),
        ),
    ]:
        groups.append(
            {
                "model": name,
                "label": label,
                "note": note,
                "cards": taxonomy_cards(TAXONOMIES[name], request),
                "add": reverse(f"admin:catalog_{name}_add"),
                "add_label": add_label,
                "can_add": request.user.has_perm(f"catalog.add_{name}"),
            }
        )
    home_admin = HomeSectionAdmin(HomeSection, admin.site)
    return TemplateResponse(
        request,
        "admin/cms/editor.html",
        {
            **admin.site.each_context(request),
            **home_admin.publication_context(request),
            "title": _("Editor visual"),
            "sections": sections,
            "groups": groups,
            "stones": next(group["cards"] for group in groups if group["model"] == "stone"),
            "home_categories": home_categories("es"),
            "device": device,
            "taxonomy_tab": request.GET.get("tab") == "taxonomy",
            "can_change_home": request.user.has_perm("cms.change_homesection"),
        },
    )


@require_POST
def action(request: HttpRequest, action: str) -> JsonResponse:
    permission = "cms.change_homesection"
    model_name = request.POST.get("model", "")
    if action == "taxonomy-cover":
        if model_name not in TAXONOMIES:
            return JsonResponse(
                {"error": _("Selecciona una categoría, piedra o colección válida.")}, status=400
            )
        permission = f"catalog.change_{model_name}"
    if not request.user.has_perm(permission):
        return JsonResponse(
            {"error": _("No tienes permiso para realizar esta acción.")}, status=403
        )
    try:
        with transaction.atomic():
            warnings: list[str] = []
            if action == "taxonomy-cover":
                obj = get_object_or_404(TAXONOMIES[model_name], pk=int(request.POST["id"]))
                obj.cover_image = cast("UploadedFile[bytes]", request.FILES["file"])
                catalog_services.save_taxonomy(
                    cast(Category | Collection | Stone, obj), actor=request.user, request=request
                )
            elif action == "sections-reorder":
                editor_services.reorder_sections(
                    ordered_ids(request), actor=request.user, request=request
                )
            else:
                section = get_object_or_404(HomeSection, pk=int(request.POST["section"]))
                if action.startswith("hero-"):
                    device = request.POST["device"]
                    if section.kind != "hero" or device not in HeroSlide.Device.values:
                        raise ValidationError(_("La portada o el dispositivo no son válidos."))
                    if action == "hero-upload":
                        warnings = editor_services.upload_hero_photos(
                            section,
                            device,
                            request.FILES.getlist("files[]"),
                            actor=request.user,
                            request=request,
                        )
                    elif action == "hero-reorder":
                        editor_services.reorder_hero_slides(
                            section,
                            device,
                            ordered_ids(request),
                            actor=request.user,
                            request=request,
                        )
                    elif action == "hero-delete":
                        slide = section.slides.filter(
                            device=device, pk=int(request.POST["id"])
                        ).first()
                        if slide is None:
                            raise ValidationError(
                                _("La foto no pertenece a esta portada y dispositivo.")
                            )
                        services.delete_hero_slide(slide, actor=request.user, request=request)
                    else:
                        raise ValueError
                elif action == "section-image":
                    editor_services.replace_section_image(
                        section,
                        cast("UploadedFile[bytes]", request.FILES["file"]),
                        actor=request.user,
                        request=request,
                    )
                elif action == "section-visibility":
                    visible = request.POST["visible"]
                    if visible not in {"true", "false"}:
                        raise ValueError
                    editor_services.set_section_visibility(
                        section, visible == "true", actor=request.user, request=request
                    )
                else:
                    raise ValueError
        return JsonResponse({"ok": True, "warnings": warnings})
    except Http404:
        return JsonResponse({"error": _("No se encontró el contenido solicitado.")}, status=404)
    except ValidationError as exc:
        return JsonResponse({"error": " ".join(exc.messages)}, status=400)
    except (ValueError, KeyError, TypeError):
        return JsonResponse(
            {"error": _("La solicitud no es válida. Recarga la página e inténtalo de nuevo.")},
            status=400,
        )


def ordered_ids(request: HttpRequest) -> list[int]:
    values = json.loads(request.POST["ids"])
    if not isinstance(values, list) or any(type(value) is not int for value in values):
        raise ValueError
    return values
