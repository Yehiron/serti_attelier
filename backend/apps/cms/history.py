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

from .documents import ContentConflict, get_document, require_capability
from .models import HomePublication, Page, PageRevision
from .review_changes import equivalent, home_groups, page_groups
from .services import restore_home, restore_page_revision


def summary(current, previous, home=False, current_source=None, previous_source=None):
    if home and current_source is not None and previous_source is not None:
        source_changes = home_source_summary(current_source, previous_source)
        if source_changes:
            return source_changes
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
                if not equivalent(old.get("title"), row.get("title")):
                    changes.append(f"Título cambiado: {old.get('title', '')} → {label}.")
                if any(
                    not equivalent(old.get(field), row.get(field)) for field in ("image", "slides")
                ):
                    changes.append(f"Fotos cambiadas en {label}.")
                if any(
                    not equivalent(old.get(field), row.get(field))
                    for field in ("body", "subtitle", "cta")
                ):
                    changes.append(f"Textos o enlaces cambiados en {label}.")
        for key, row in before.items():
            if key not in after:
                changes.append(f"Sección oculta o retirada: {row.get('title') or 'Sección'}.")
        common = before.keys() & after.keys()
        if [key for key in before if key in common] != [key for key in after if key in common]:
            changes.append("Secciones reordenadas.")
        # Repeat the same semantic comparison for English, even when Spanish changed too.
        if current.get("en") != previous.get("en"):
            english = summary(
                {"es": current.get("en", [])}, {"es": previous.get("en", [])}, home=True
            )
            changes.extend(
                f"{item} (inglés)"
                for item in english
                if item != "Sin cambios visibles en la tienda."
            )
    else:
        for locale, language in (("es", "español"), ("en", "inglés")):
            old, new = previous.get(locale, {}), current.get(locale, {})
            for field, label, state in (
                ("title", "Título", "actualizado"),
                ("slug", "Dirección", "actualizada"),
                ("body", "Contenido", "actualizado"),
                ("process", "Pasos", "actualizados"),
                ("faq", "Preguntas frecuentes", "actualizadas"),
            ):
                if not equivalent(old.get(field), new.get(field)):
                    changes.append(
                        f"{label} en {language} {state}"
                        + (
                            f": {old.get(field, '')} → {new.get(field, '')}. "
                            if field == "title"
                            else "."
                        )
                    )
                    if field in {"body", "slug"}:
                        changes.append(
                            f"{label} ({language}): {excerpt(old.get(field))} → "
                            f"{excerpt(new.get(field))}."
                        )
                    elif field in {"process", "faq"}:
                        before, after = (
                            v if isinstance(v, dict) else {}
                            for v in (old.get(field), new.get(field))
                        )
                        if before.get("title") != after.get("title"):
                            changes.append(
                                f"{label} · Encabezado ({language}): "
                                f"{excerpt(before.get('title'))} → {excerpt(after.get('title'))}."
                            )
                        list_key = "steps" if field == "process" else "items"
                        fields = (
                            (("title", "Título"), ("description", "Descripción"))
                            if field == "process"
                            else (("question", "Pregunta"), ("answer", "Respuesta"))
                        )
                        old_rows, new_rows = before.get(list_key, []), after.get(list_key, [])
                        for index in range(max(len(old_rows), len(new_rows))):
                            left = old_rows[index] if index < len(old_rows) else {}
                            right = new_rows[index] if index < len(new_rows) else {}
                            left = left if isinstance(left, dict) else {}
                            right = right if isinstance(right, dict) else {}
                            left, right = left.get("source", left), right.get("source", right)
                            for name, field_label in fields:
                                if left.get(name) != right.get(name):
                                    changes.append(
                                        f"{label} {index + 1} · {field_label} ({language}): "
                                        f"{excerpt(left.get(name))} → {excerpt(right.get(name))}."
                                    )
    return changes or ["Sin cambios visibles en la tienda."]


def excerpt(value):
    return " ".join(str(value or "Sin contenido").split())[:120]


def home_source_summary(current, previous):
    """Editable source includes hidden sections, original translations and slide order."""
    before = {row["id"]: row for row in previous}
    after = {row["id"]: row for row in current}
    changes = []
    for key, row in after.items():
        label = (
            row.get("title_es")
            or row.get("props", {}).get("title", {}).get("es")
            or row.get("title")
            or "Sección"
        )
        old = before.get(key)
        if old is None:
            suffix = " (oculta)" if not row.get("is_visible", True) else ""
            changes.append(f"Sección añadida{suffix}: {label}.")
            if row.get("image") or row.get("slides"):
                changes.append(f"Fotos añadidas en {label}.")
            continue
        if old.get("is_visible", True) != row.get("is_visible", True):
            state = "mostrada" if row.get("is_visible", True) else "oculta"
            changes.append(f"Sección {state}: {label}.")
        for locale, language in (("es", "español"), ("en", "inglés")):
            title = f"title_{locale}"
            if not equivalent(old.get(title), row.get(title)):
                changes.append(
                    f"Título en {language} cambiado en {label}: "
                    f"{old.get(title) or 'Sin título'} → {row.get(title) or 'Sin título'}."
                )
            if any(
                not equivalent(old.get(f"{field}_{locale}"), row.get(f"{field}_{locale}"))
                for field in ("body", "subtitle", "cta_label", "image_alt")
            ):
                for field in ("body", "subtitle", "cta_label", "image_alt"):
                    name = f"{field}_{locale}"
                    if not equivalent(old.get(name), row.get(name)):
                        field_label = {
                            "body": "Texto",
                            "subtitle": "Subtítulo",
                            "cta_label": "Texto del enlace",
                            "image_alt": "Texto alternativo",
                        }[field]
                        changes.append(
                            f"{label} · {field_label} ({language}): "
                            f"{str(old.get(name) or 'Sin contenido')[:120]} → "
                            f"{str(row.get(name) or 'Sin contenido')[:120]}."
                        )
        if any(
            not equivalent(old.get(field), row.get(field))
            for field in ("image", "slides", "renditions")
        ):
            changes.append(f"Fotos cambiadas o reordenadas en {label}.")
        if old.get("props", {}) != row.get("props", {}):
            from .registry import REGISTRY, editorial_props

            spec = REGISTRY.get(row.get("kind"))
            if spec:
                old_values = editorial_props(spec.kind, old.get("props", {}))
                new_values = editorial_props(spec.kind, row.get("props", {}))
                for change_label in dict.fromkeys((*old_values, *new_values)):
                    if not equivalent(old_values.get(change_label), new_values.get(change_label)):
                        changes.append(
                            f"{spec.name} · {change_label}: "
                            f"{str(old_values.get(change_label, 'Sin contenido'))[:120]} → "
                            f"{str(new_values.get(change_label, 'Sin contenido'))[:120]}."
                        )
        destinations = {
            field for field in row if field.startswith("cta_") and not field.startswith("cta_label")
        } | {"collection_id"}
        if any(not equivalent(old.get(field), row.get(field)) for field in destinations):
            changes.append(f"Destino de enlaces o colección cambiado en {label}.")
    for key, row in before.items():
        if key not in after:
            changes.append(
                f"Sección retirada: {row.get('title_es') or row.get('title') or 'Sección'}."
            )
    common = before.keys() & after.keys()
    if [key for key in before if key in common] != [key for key in after if key in common]:
        changes.append("Secciones reordenadas.")
    return changes


def document(request):
    require_capability(request.user, "edit")
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
        "can_restore": request.user.has_perm("cms.restore_content"),
    }
    content_document = get_document(
        "home" if key == "home" else f"page:{Page.objects.get(pk=key).kind}"
    )
    context["editor_url"] = reverse("visual-editor") + f"?document={content_document.key}"
    from .publishing import preview_url

    context["preview_url"] = preview_url(request, content_document.key)
    context["expected_version"] = content_document.draft_version
    context["restorations"] = content_document.draft_revisions.select_related(
        "restored_from_home", "restored_from_page"
    )[:20]
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
            try:
                if key == "home":
                    restore_home(
                        revision,
                        request.user,
                        request,
                        expected_version=request.POST.get("expected_version"),
                    )
                else:
                    restore_page_revision(
                        revision,
                        request.user,
                        request,
                        expected_version=request.POST.get("expected_version"),
                    )
            except ContentConflict as exc:
                context["conflict"] = " ".join(exc.messages)
                context["current_url"] = reverse("cms-history") + f"?document={key}"
                context["expected_version"] = request.POST.get("expected_version", "")
            else:
                messages.success(
                    request, "Versión restaurada como borrador. La tienda no ha cambiado."
                )
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
                    current_source=getattr(row, "draft_snapshot", None),
                    previous_source=getattr(
                        rows[index + 1] if index + 1 < len(rows) else older, "draft_snapshot", None
                    ),
                ),
            }
            for index, row in enumerate(rows)
        ]
        for index, item in enumerate(context["rows"]):
            prior = rows[index + 1] if index + 1 < len(rows) else older
            item["change_groups"] = (
                home_groups(item["publication"].draft_snapshot, prior.draft_snapshot)
                if key == "home"
                and prior
                and item["publication"].draft_snapshot is not None
                and prior.draft_snapshot is not None
                else page_groups(item["publication"].snapshot, prior.snapshot)
                if key != "home" and prior
                else []
            )
    return TemplateResponse(
        request, "admin/cms/history.html", context, status=409 if context.get("conflict") else 200
    )
