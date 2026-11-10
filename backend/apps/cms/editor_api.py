"""Session + CSRF API for the three panel editor (no public write surface)."""

import json
from urllib.parse import urlencode

from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404, JsonResponse
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie

from apps.catalog.models import Category, Collection, Piece, Stone

from . import services, visual_documents
from .documents import ContentConflict, edit_document, lock_document, require_capability
from .menus import MENU_KEYS, restore_menu
from .models import Page
from .page_options import LEGAL_KINDS, draft_path
from .preview import make_token
from .publishing import pending_changes


@ensure_csrf_cookie
def editor(request):
    require_capability(request.user, "edit")
    from .forms import PhotoInput

    return TemplateResponse(
        request,
        "admin/cms/editor.html",
        {
            **admin.site.each_context(request),
            "title": "Editor de la página web",
            "api_url": reverse("cms-editor-document"),
            "can_publish": request.user.has_perm("cms.publish_content"),
            "can_restore": request.user.has_perm("cms.restore_content"),
            "history_url": reverse("cms-history"),
            "photo_widget": PhotoInput().render(
                "photo", None, attrs={"id": "cms-photo-template", "accept": "image/*"}
            ),
        },
    )


def state(key, request):
    document = lock_document(key)
    sections = visual_documents.read_sections(key)
    page = visual_documents.page_for(key) if key.startswith("page:") else None
    if key not in MENU_KEYS:
        sections.append({"id": "seo", "kind": "seo", "visible": True, "values": document.seo})
    preview = {}
    if request.user.has_perm("cms.preview_content"):
        token = make_token(request.user)
        for lang in ("es", "en"):
            path = f"/{lang}" if page is None else draft_path(page, lang)
            preview[lang] = "/preview?" + urlencode({"token": token, "path": path})
    choices = {}
    for kind, model in (
        ("category", Category),
        ("collection", Collection),
        ("piece", Piece),
        ("stone", Stone),
        ("page", Page),
    ):
        rows = model.objects.all()
        choices[kind] = [
            {"id": row.pk, "name": getattr(row, "name_es", None) or getattr(row, "title_es", "")}
            for row in rows
        ]
    return {
        "translation_exemptions": document.translation_exemptions,
        "can_noindex": request.user.has_perm("cms.publish_content"),
        "personalize_body_hidden": bool(
            page and page.kind == "personalize" and not page.body_enabled
        ),
        "paths": {lang: draft_path(page, lang) for lang in ("es", "en")} if page else {},
        "legal": {
            "version": page.version,
            "updated_at": page.published_at.isoformat() if page.published_at else None,
        }
        if page and page.kind in LEGAL_KINDS
        else None,
        "key": key,
        "version": document.draft_version,
        "sections": sections,
        "registry": visual_documents.applicable_registry(key),
        "documents": [
            {"key": "home", "name": "Inicio"},
            {"key": "menu:main", "name": "Menú principal"},
            {"key": "menu:footer", "name": "Menú del pie de página"},
            *[{"key": f"page:{p.kind}", "name": p.title_es} for p in Page.objects.all()],
        ],
        "pending": pending_changes(key)["count"],
        "preview": preview,
        "choices": choices,
        "review_url": reverse("cms-review-publish", args=[key]),
        "can_discard": request.user.has_perm("cms.restore_content")
        and bool(
            document.menu_publication_id
            if key in MENU_KEYS
            else document.home_publication_id
            if key == "home"
            else document.page_revision_id
        ),
    }


@never_cache
@csrf_protect
@transaction.atomic
def document(request):
    if (
        not request.user.is_authenticated
        or not request.user.is_active
        or not request.user.is_staff
        or not request.user.has_perm("cms.edit_content")
    ):
        return JsonResponse({"error": "No tienes permiso para editar esta página."}, status=403)
    if request.method not in ("GET", "POST"):
        return JsonResponse({"error": "Usa una solicitud de lectura o guardado."}, status=405)
    key = request.GET.get("document", "home")
    try:
        # Reject unknown keys before creating the document row.
        if key != "home" and key not in MENU_KEYS:
            visual_documents.page_for(key)
        created = None
        if request.method == "POST":
            data = json.loads(request.body)
            action = data.get("action")
            if action == "discard":
                require_capability(request.user, "restore")
                doc = lock_document(key)
                origin = (
                    doc.menu_publication
                    if key in MENU_KEYS
                    else doc.home_publication
                    if key == "home"
                    else doc.page_revision
                )
                if not origin:
                    raise ValidationError("Todavía no hay una publicación para recuperar.")
                (
                    restore_menu
                    if key in MENU_KEYS
                    else services.restore_home
                    if key == "home"
                    else services.restore_page_revision
                )(origin, request.user, request, expected_version=data.get("expected_version"))
            else:
                with edit_document(key, request.user, data.get("expected_version")):
                    created = visual_documents.mutate(key, action, data, request.user, request)
        response = JsonResponse({**state(key, request), "selected": created})
        response["Cache-Control"] = "private, no-store"
        return response
    except ContentConflict as exc:
        return JsonResponse(
            {
                "conflict": True,
                "error": "Otra persona guardó cambios en esta página",
                "version": exc.document.draft_version,
            },
            status=409,
        )
    except PermissionDenied:
        return JsonResponse({"error": "No tienes permiso para realizar esta acción."}, status=403)
    except Http404:
        return JsonResponse({"error": "No se encontró el contenido solicitado."}, status=404)
    except ValidationError as exc:
        return JsonResponse(
            {
                "error": "Revisa los campos señalados.",
                "fields": exc.message_dict
                if hasattr(exc, "message_dict")
                else {"__all__": exc.messages},
            },
            status=400,
        )
    except (ValueError, TypeError, KeyError, AttributeError):
        return JsonResponse({"error": "La solicitud no es válida. Revisa los campos."}, status=400)


@never_cache
@csrf_protect
@transaction.atomic
def photo(request):
    from django.shortcuts import get_object_or_404

    from . import editor_services
    from .models import HomeSection
    from .registry import get_type

    try:
        require_capability(request.user, "edit")
        if request.method != "POST":
            return JsonResponse({"error": "Usa el botón para subir una foto."}, status=405)
        with edit_document("home", request.user, request.POST.get("expected_version")):
            slot = request.POST.get("slot")
            section_id = request.POST.get("section")
            section = None if section_id == "new" else get_object_or_404(HomeSection, pk=section_id)
            image = None
            if slot and section and get_type(section.kind).storage == "columns":
                if slot != "image":
                    raise ValidationError("Esta foto no corresponde a esta sección.")
                editor_services.replace_section_image(
                    section,
                    request.FILES["file"],
                    actor=request.user,
                    request=request,
                    alt={
                        "es": request.POST.get("alt_es", ""),
                        "en": request.POST.get("alt_en", ""),
                    },
                )
            elif slot:
                kind = section.kind if section else request.POST.get("kind")
                field = next(
                    (f for f in get_type(kind).fields if f.key == slot and f.type == "image"), None
                )
                if not field or get_type(kind).storage == "columns":
                    raise ValidationError("Esta sección no admite esta foto.")
                image = editor_services.upload_editor_image(
                    request.FILES["file"],
                    {"es": request.POST.get("alt_es", ""), "en": request.POST.get("alt_en", "")},
                    actor=request.user,
                    request=request,
                )
                if section:
                    section.props = {**section.props, slot: image}
                    services.save_section(section, actor=request.user, request=request)
            elif section and section.kind == "hero":
                editor_services.upload_hero_photos(
                    section,
                    request.POST.get("device", "desktop"),
                    request.FILES.getlist("file"),
                    actor=request.user,
                    request=request,
                )
            elif section:
                editor_services.replace_section_image(
                    section,
                    request.FILES["file"],
                    actor=request.user,
                    request=request,
                    alt={
                        "es": request.POST.get("alt_es", ""),
                        "en": request.POST.get("alt_en", ""),
                    },
                )
            else:
                raise ValidationError("Selecciona primero una sección.")
        return JsonResponse({**state("home", request), "image": image})
    except ContentConflict:
        return JsonResponse(
            {"conflict": True, "error": "Otra persona guardó cambios en esta página"}, status=409
        )
    except PermissionDenied:
        return JsonResponse({"error": "No tienes permiso para subir fotos."}, status=403)
    except (ValidationError, KeyError, ValueError, Http404) as exc:
        return JsonResponse(
            {
                "error": " ".join(exc.messages)
                if isinstance(exc, ValidationError)
                else "Selecciona una foto y una sección válidas."
            },
            status=400,
        )
