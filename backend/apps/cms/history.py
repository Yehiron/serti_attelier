"""Readable publication history; immutable technical screens remain separate."""

from zoneinfo import ZoneInfo

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect

from .models import HomePublication, Page, PageRevision
from .services import restore_home, restore_page_revision


def summary(current, previous, home=False):
    if previous is None:
        return ["Primera publicación guardada."]
    changes = []
    if home:
        before = {row["id"]: row for row in previous.get("es", [])}
        after = {row["id"]: row for row in current.get("es", [])}
        for key, row in after.items():
            label = row.get("title") or "Sección"
            if key not in before:
                changes.append(f"Sección añadida o mostrada: {label}.")
            else:
                old = before[key]
                if old.get("title") != row.get("title"):
                    changes.append(f"Título cambiado: {old.get('title', '')} → {label}.")
                if any(old.get(field) != row.get(field) for field in ("image", "slides")):
                    changes.append(f"Fotos cambiadas en {label}.")
                if any(old.get(field) != row.get(field) for field in ("body", "subtitle", "cta")):
                    changes.append(f"Textos o enlaces cambiados en {label}.")
        for key, row in before.items():
            if key not in after:
                changes.append(f"Sección oculta o retirada: {row.get('title') or 'Sección'}.")
        common = before.keys() & after.keys()
        if [key for key in before if key in common] != [key for key in after if key in common]:
            changes.append("Secciones reordenadas.")
        if current.get("en") != previous.get("en") and not changes:
            changes.append("Contenido en inglés actualizado.")
    else:
        for locale, language in (("es", "español"), ("en", "inglés")):
            old, new = previous.get(locale, {}), current.get(locale, {})
            for field, label in (
                ("title", "Título"),
                ("slug", "Dirección"),
                ("body", "Contenido"),
                ("process", "Pasos"),
                ("faq", "Preguntas frecuentes"),
            ):
                if old.get(field) != new.get(field):
                    changes.append(
                        f"{label} en {language} actualizado"
                        + (
                            f": {old.get(field, '')} → {new.get(field, '')}. "
                            if field == "title"
                            else "."
                        )
                    )
    return changes or ["Sin cambios visibles en la tienda."]


def document(request):
    key = request.GET.get(
        "document",
        "home"
        if request.user.has_perm("cms.view_homepublication")
        else str(Page.objects.order_by("pk").values_list("pk", flat=True).first() or "0"),
    )
    if key == "home":
        if not request.user.has_perm("cms.view_homepublication"):
            raise PermissionDenied
        return key, "Inicio", HomePublication.objects.all()
    if not request.user.has_perm("cms.view_pagerevision"):
        raise PermissionDenied
    page = get_object_or_404(Page, pk=key if key.isdecimal() else 0)
    return key, page.title_es, PageRevision.objects.filter(page=page)


@csrf_protect
def history(request):
    key, title, queryset = document(request)
    context = {
        **admin.site.each_context(request),
        "title": "Historial de publicaciones",
        "document": key,
        "document_title": title,
        "show_home": request.user.has_perm("cms.view_homepublication"),
        "documents": Page.objects.only("id", "title_es")
        if request.user.has_perm("cms.view_pagerevision")
        else [],
        "can_restore": request.user.has_perm("cms.publish_content"),
    }
    revision_id = request.GET.get("restore")
    if revision_id:
        if not context["can_restore"]:
            raise PermissionDenied
        revision = get_object_or_404(queryset, pk=revision_id if revision_id.isdecimal() else 0)
        date = timezone.localtime(revision.published_at, ZoneInfo("America/Bogota")).strftime(
            "%d/%m/%Y a las %H:%M"
        )
        if request.method == "POST":
            if request.POST.get("confirm") != "yes":
                raise PermissionDenied
            if key == "home":
                restore_home(revision, request.user, request)
            else:
                restore_page_revision(revision, request.user, request)
            messages.success(request, "Versión restaurada como borrador. La tienda no ha cambiado.")
            return HttpResponseRedirect(reverse("cms-history") + f"?document={key}")
        context.update(
            confirmation=(
                f"Esto reemplaza tu borrador actual por la versión del {date}. "
                "La tienda no cambia hasta que publiques."
            )
        )
    else:
        if request.method != "GET":
            raise PermissionDenied
        page = Paginator(queryset, 20).get_page(request.GET.get("page"))
        # Fetch one predecessor for the whole page, avoiding one query per publication.
        rows = list(page.object_list)
        older = queryset.filter(pk__lt=rows[-1].pk).first() if rows else None
        context["page_obj"] = page
        context["rows"] = [
            {
                "publication": row,
                "date": timezone.localtime(row.published_at, ZoneInfo("America/Bogota")),
                "changes": summary(
                    row.snapshot,
                    (rows[index + 1] if index + 1 < len(rows) else older).snapshot
                    if index + 1 < len(rows) or older
                    else None,
                    key == "home",
                ),
            }
            for index, row in enumerate(rows)
        ]
    return TemplateResponse(request, "admin/cms/history.html", context)
