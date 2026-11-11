"""Review selectors shared by today's editor and the future document editor."""

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect

from . import services
from .documents import ContentConflict, lock_document, require_capability
from .models import HomePublication, Page

_UNSET = object()


def pending_changes(key, *, previous=_UNSET):
    from .documents import get_document
    from .history import summary
    from .menus import MENU_KEYS, menu_groups
    from .page_options import seo_groups
    from .review_changes import change_lines, equivalent, home_groups, page_groups
    from .selectors import draft_sections, render_sections

    doc = get_document(key)
    groups = []
    if key == "brand:identity":
        from .brand import groups as brand_groups

        snapshot = doc.brand_identity
        groups = brand_groups(
            snapshot, doc.brand_publication.snapshot if doc.brand_publication else {}
        )
        changes = change_lines(groups)
    elif key in MENU_KEYS:
        snapshot = doc.menu_items
        groups = menu_groups(
            snapshot, doc.menu_publication.snapshot if doc.menu_publication else []
        )
        changes = change_lines(groups)
    elif key == "home":
        rows = list(draft_sections())
        snapshot = {lang: render_sections(rows, lang) for lang in ("es", "en")}
        source = [services.section_source(row) for row in rows]
        if previous is _UNSET:
            previous = HomePublication.objects.first()
        from .section_adapters import home_snapshot, section_sources

        if (
            previous
            and equivalent(home_snapshot(previous.snapshot), snapshot)
            and (
                previous.draft_snapshot is None
                or equivalent(section_sources(previous.draft_snapshot), source)
            )
        ):
            changes = []
        else:
            changes = summary(
                snapshot,
                previous.snapshot if previous else None,
                home=True,
                current_source=source,
                previous_source=previous.draft_snapshot if previous else None,
            )
            if (
                previous
                and previous.draft_snapshot is not None
                and not equivalent(previous.draft_snapshot, source)
                and changes == ["Sin cambios visibles en la tienda."]
            ):
                changes = ["Contenido de secciones ocultas o configuración del inicio actualizado."]
        if (
            previous
            and previous.draft_snapshot is None
            and changes == ["Sin cambios visibles en la tienda."]
        ):
            changes = []
        if previous and previous.draft_snapshot is not None:
            groups = home_groups(source, previous.draft_snapshot)
            changes = change_lines(groups)
    else:
        page = Page.objects.get(kind=key.removeprefix("page:"))
        snapshot = services.page_snapshot(page)
        previous = page.revisions.first()
        changes = (
            []
            if previous and previous.snapshot == snapshot
            else summary(snapshot, previous.snapshot if previous else None)
        )
        if previous:
            groups = page_groups(snapshot, previous.snapshot, kind=page.kind)
            changes = change_lines(groups)
    if key not in MENU_KEYS and key != "brand:identity":
        previous_seo = (
            previous.seo
            if key == "home" and previous
            else previous.snapshot.get("_seo", {})
            if previous
            else {}
        )
        extra = seo_groups(doc.seo, previous_seo)
        if extra:
            groups.extend(extra)
            changes = change_lines(groups)
    if changes and not groups:
        groups = [
            {
                "name": "Documento",
                "icon": "article",
                "rows": [
                    {"label": line, "before": "", "after": "Pendiente de publicación"}
                    for line in changes
                ],
            }
        ]
    return {"count": len(changes), "changes": changes, "groups": groups, "snapshot": snapshot}


@csrf_protect
@transaction.atomic
def review_publish(request, key):
    require_capability(request.user, "publish")
    from .menus import MENU_KEYS, publish_menu

    if key == "brand:identity":
        page, title = None, "Identidad de marca"
    elif key in MENU_KEYS:
        page, title = None, "Menú principal" if key == "menu:main" else "Menú del pie de página"
    elif key != "home":
        page = get_object_or_404(Page, kind=key.removeprefix("page:"))
        key = f"page:{page.kind}"
        title = page.title_es
    else:
        page, title = None, "Inicio"
    if key.startswith("page:"):
        lock_document("home")
    document = lock_document(key)
    error = ""
    status = 200
    note = request.POST.get("note", "")
    if request.method == "POST":
        try:
            # Service checks the version even for submissions with no pending changes.
            with transaction.atomic():
                if key == "brand:identity":
                    from .brand import publish

                    publish(
                        request.user,
                        request,
                        note=note,
                        expected_version=request.POST.get("expected_version"),
                    )
                elif key in MENU_KEYS:
                    publish_menu(
                        key,
                        request.user,
                        request,
                        note=note,
                        expected_version=request.POST.get("expected_version"),
                    )
                elif page:
                    services.publish_page(
                        page,
                        request.user,
                        request,
                        note=note,
                        expected_version=request.POST.get("expected_version"),
                    )
                else:
                    services.publish_home(
                        request.user,
                        request,
                        note=note,
                        expected_version=request.POST.get("expected_version"),
                    )
            messages.success(request, "Publicación guardada. La tienda ya muestra esta versión.")
            return HttpResponseRedirect(
                reverse("cms-history")
                + (
                    f"?document={key}"
                    if key in MENU_KEYS or key == "brand:identity"
                    else f"?document={page.pk}"
                    if page
                    else "?document=home"
                )
            )
        except ContentConflict as exc:
            error, status = " ".join(exc.messages), 409
        except ValidationError as exc:
            error, status = " ".join(exc.messages), 400
    brand_failures = []
    if key == "brand:identity":
        from .brand import checks

        brand_failures = [
            row for row in checks(document.brand_identity) if row["required"] and not row["ok"]
        ]
    pending = pending_changes(key)
    return TemplateResponse(
        request,
        "admin/cms/review_publish.html",
        {
            **admin.site.each_context(request),
            "title": "Revisar y publicar",
            "document_title": title,
            "is_brand": key == "brand:identity",
            "brand_failures": brand_failures,
            "editor_url": reverse("visual-editor") + f"?document={key}",
            "expected_version": document.draft_version,
            "changes": pending["changes"],
            "change_groups": pending["groups"],
            "preview_url": preview_url(request, key),
            "pending_count": pending["count"],
            "error": error,
            "note": note,
            "current_url": reverse("cms-review-publish", args=[key]),
        },
        status=status,
    )


def preview_url(request, key):
    from urllib.parse import urlencode

    from .preview import make_token

    if not request.user.has_perm("cms.preview_content"):
        return ""
    from .page_options import draft_path

    page = Page.objects.get(kind=key[5:]) if key.startswith("page:") else None
    path = "/es" if page is None else draft_path(page, "es")
    return "/preview?" + urlencode({"token": make_token(request.user), "path": path})
