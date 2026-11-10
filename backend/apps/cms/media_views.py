"""Staff-only library. JSON errors never contain filesystem paths or upload names."""

import json
from functools import wraps

from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from rest_framework.throttling import SimpleRateThrottle

from apps.audit.services import record

from . import media
from .documents import require_capability
from .models import MediaAsset


class UploadThrottle(SimpleRateThrottle):
    scope = "cms_media_upload"
    rate = "30/min"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": str(request.user.pk)}


class MediaConflict(Exception):
    pass


def protected(view):
    @wraps(view)
    @never_cache
    @csrf_protect
    def wrapped(request, *args, **kwargs):
        try:
            require_capability(request.user, "edit")
            return view(request, *args, **kwargs)
        except PermissionDenied:
            return JsonResponse({"error": "No tienes permiso para usar la biblioteca."}, status=403)
        except Http404:
            return JsonResponse({"error": "Esta foto ya no está disponible."}, status=404)
        except MediaConflict:
            return JsonResponse(
                {"conflict": True, "error": "Otra persona guardó esta foto. Vuelve a abrirla."},
                status=409,
            )
        except (ValidationError, ValueError, TypeError, KeyError) as exc:
            message = (
                " ".join(exc.messages)
                if isinstance(exc, ValidationError)
                else "Revisa los datos de la foto."
            )
            return JsonResponse({"error": message}, status=400)

    return wrapped


def payload(asset, sources=None):
    generation = asset.versions.get(str(asset.version), {})
    image = next(iter(generation.values()), {})
    paths = image.get("paths", {})
    thumbnail = (
        media.default_storage.url(paths[min(paths, key=int)]) if paths else image.get("src", "")
    )
    return {
        "id": asset.pk,
        "title": asset.title,
        "tags": asset.tags,
        "alt_es": asset.alt_es,
        "alt_en": asset.alt_en,
        "width": asset.width,
        "height": asset.height,
        "size": asset.size,
        "focal_x": asset.focal_x,
        "focal_y": asset.focal_y,
        "crops": asset.crops,
        "state": asset.state,
        "version": asset.version,
        "archived": asset.archived,
        "thumbnail": thumbnail,
        "original": asset.original.url,
        "ratios": media.ratios(),
        "usage": media.used_by(asset, sources) if sources is not None else [],
    }


@protected
def library(request):
    return TemplateResponse(
        request,
        "admin/cms/media.html",
        {
            **admin.site.each_context(request),
            "title": "Biblioteca de fotos",
            "media_api": reverse("cms-media-api"),
        },
    )


@protected
def assets(request):
    if request.method == "GET":
        rows = MediaAsset.objects.all()
        search = request.GET.get("q", "")[:300]
        if search:
            rows = rows.filter(
                Q(title__icontains=search)
                | Q(tags__icontains=search)
                | Q(alt_es__icontains=search)
                | Q(alt_en__icontains=search)
            )
        sources = media.all_usage()
        mode = request.GET.get("filter", "")
        rows = rows.filter(archived=mode == "archived")
        if mode in {"used", "unused"}:
            rows = [row for row in rows if bool(media.used_by(row, sources)) == (mode == "used")]
        page = Paginator(rows, 40).get_page(request.GET.get("page", 1))
        return JsonResponse(
            {
                "items": [payload(row, sources) for row in page],
                "page": page.number,
                "pages": page.paginator.num_pages,
            }
        )
    if request.method == "POST":
        if not UploadThrottle().allow_request(request, None):
            return JsonResponse(
                {"error": "Has subido muchas fotos. Espera un minuto antes de continuar."},
                status=429,
            )
        files = request.FILES.getlist("file")
        if not 1 <= len(files) <= 10:
            raise ValidationError("Sube de una a diez fotos por vez.")
        items = []
        for file in files:
            try:
                asset, duplicate = media.upload(file, request.user, request)
                items.append({"asset": payload(asset), "duplicate": duplicate})
            except ValidationError as exc:
                items.append({"error": " ".join(exc.messages)})
        return JsonResponse({"items": items})
    return JsonResponse({"error": "Acción no disponible."}, status=405)


@protected
@transaction.atomic
def detail(request, pk):
    asset = get_object_or_404(MediaAsset.objects.select_for_update(of=("self",)), pk=pk)
    if request.method == "GET":
        return JsonResponse(payload(asset, media.all_usage()))
    if request.method != "POST":
        return JsonResponse({"error": "Acción no disponible."}, status=405)
    data = json.loads(request.body)
    if not isinstance(data, dict):
        raise ValidationError("Revisa los datos de la foto.")
    if str(data.get("expected_version")) != str(asset.version):
        raise MediaConflict
    action = data.get("action", "save")
    if action == "delete":
        media.remove(asset, request.user, request)
        return JsonResponse({"deleted": True})
    if action == "archive":
        asset.archived = not asset.archived
        generation = asset.versions.get(str(asset.version))
        asset.version += 1
        if generation:
            asset.versions = {**asset.versions, str(asset.version): generation}
        asset.save(update_fields=["archived", "version", "versions", "updated_at"])
        record("cms.media_archived", actor=request.user, obj=asset, request=request)
    elif action in {"save", "retry"}:
        if action == "save":
            for key, limit in (("title", 200), ("tags", 300), ("alt_es", 300), ("alt_en", 300)):
                value = data.get(key, getattr(asset, key))
                if not isinstance(value, str) or len(value) > limit:
                    raise ValidationError(f"Usa hasta {limit} caracteres en los textos de la foto.")
                setattr(asset, key, value)
            asset.focal_x = data.get("focal_x", asset.focal_x)
            asset.focal_y = data.get("focal_y", asset.focal_y)
            asset.crops = data.get("crops", asset.crops)
            media.validate_adjustments(
                asset.focal_x, asset.focal_y, asset.crops, asset.width, asset.height
            )
            asset.version += 1
        asset.state = "processing"
        asset.save()
        record("cms.media_saved", actor=request.user, obj=asset, request=request)
        transaction.on_commit(lambda: media.enqueue(asset.pk, asset.version))
    else:
        raise ValidationError("Selecciona una acción disponible.")
    return JsonResponse(payload(asset, media.all_usage()))
