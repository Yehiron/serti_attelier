"""Owner-facing redirect management and untranslated editorial texts."""

from urllib.parse import urlencode

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from .documents import ContentConflict, get_document, require_capability
from .models import ContentDocument, MediaAsset, Page, Redirect
from .redirects import save_redirect
from .visual_documents import read_sections


class RedirectForm(forms.ModelForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)

    class Meta:
        model = Redirect
        fields = ["from_path", "to_path", "status_code", "is_active"]
        help_texts = {
            "from_path": "Por ejemplo: /es/antigua-direccion",
            "to_path": "La dirección completa de una página que ya exista en la tienda.",
        }


@never_cache
@csrf_protect
def redirects(request):
    require_capability(request.user, "edit")
    can_change = request.user.has_perm("cms.publish_content")
    pk = request.GET.get("edit")
    obj = get_object_or_404(Redirect, pk=pk) if pk else None
    doc = get_document("redirects")
    form = RedirectForm(
        request.POST or None, instance=obj, initial={"expected_version": doc.draft_version}
    )
    status = 200
    if request.method == "POST":
        if not can_change:
            raise PermissionDenied
        if form.is_valid():
            try:
                save_redirect(
                    form.save(commit=False),
                    request.user,
                    request,
                    expected_version=form.cleaned_data["expected_version"],
                )
            except ContentConflict as exc:
                form.add_error(None, " ".join(exc.messages))
                status = 409
            except ValidationError as exc:
                form.add_error(None, " ".join(exc.messages))
                status = 400
            else:
                messages.success(
                    request,
                    "Redirección guardada. La tienda la recibirá en un máximo de un minuto.",
                )
                return HttpResponseRedirect(reverse("cms-redirect-management"))
        else:
            status = 400
    elif request.method != "GET":
        raise PermissionDenied
    query = request.GET.get("q", "")[:200]
    rows = Redirect.objects.filter(Q(from_path__icontains=query) | Q(to_path__icontains=query))
    return TemplateResponse(
        request,
        "admin/cms/redirects.html",
        {
            **admin.site.each_context(request),
            "title": "Redirecciones",
            "rows": rows,
            "form": form,
            "can_change": can_change,
            "query": query,
        },
        status=status,
    )


def missing_pairs(value, path=""):
    if isinstance(value, dict):
        if "es" in value and isinstance(value["es"], str):
            es, en = value["es"].strip(), (value.get("en") or "").strip()
            if es and (not en or en == es):
                yield path, es, en
        else:
            for key, item in value.items():
                yield from missing_pairs(item, f"{path}.{key}".strip("."))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from missing_pairs(item, f"{path}.{index}".strip("."))


def document_pending_translations(key, document):
    from .visual_documents import applicable_registry

    names = {spec["kind"]: spec["name"] for spec in applicable_registry(key)}
    labels = {
        "title": "Título",
        "body": "Contenido",
        "subtitle": "Subtítulo",
        "label": "Etiqueta del enlace",
        "question": "Pregunta",
        "answer": "Respuesta",
        "description": "Descripción",
        "alt": "Texto alternativo",
        "image_alt": "Texto alternativo",
        "cta_label": "Texto del enlace",
    }
    sections = read_sections(key)
    if not key.startswith("menu:"):
        sections.append({"id": "seo", "kind": "seo", "values": document.seo})
    items = []
    for section in sections:
        for path, es, en in missing_pairs(section["values"]):
            # Addresses are translated independently but aren't prose translations.
            if path == "slug" or (
                document.translation_exemptions.get(f"{section['id']}.{path}") == es and es == en
            ):
                continue
            items.append(
                {
                    "section": names.get(section["kind"], "Sección"),
                    "label": labels.get(path.split(".")[-1], "Texto")
                    + (" SEO" if section["id"] == "seo" else ""),
                    "es": es,
                    "en": en,
                    "url": reverse("visual-editor")
                    + "?"
                    + urlencode(
                        {
                            "document": key,
                            "section": section["id"],
                            "field": path,
                            "language": "en",
                        }
                    ),
                }
            )
    return items


def pending_translations():
    groups = []
    documents = {doc.key: doc for doc in ContentDocument.objects.all()}
    keys = [
        ("home", "Inicio"),
        ("menu:main", "Menú principal"),
        ("menu:footer", "Menú del pie de página"),
    ]
    keys += [(f"page:{p.kind}", p.title_es) for p in Page.objects.all()]
    for key, name in keys:
        if key not in documents:
            continue
        items = document_pending_translations(key, documents[key])
        if items:
            groups.append({"name": name, "items": items})
    photos = [
        {
            "label": "Texto alternativo",
            "es": asset.alt_es,
            "en": asset.alt_en,
            "url": reverse("cms-media") + "?" + urlencode({"asset": asset.pk, "language": "en"}),
        }
        for asset in MediaAsset.objects.all()
        if asset.alt_es.strip()
        and (not asset.alt_en.strip() or asset.alt_es.strip() == asset.alt_en.strip())
    ]
    if photos:
        groups.append({"name": "Biblioteca de fotos", "items": photos})
    return groups


@never_cache
def translations(request):
    require_capability(request.user, "edit")
    if request.method != "GET":
        raise PermissionDenied
    groups = pending_translations()
    return TemplateResponse(
        request,
        "admin/cms/translations.html",
        {
            **admin.site.each_context(request),
            "title": "Traducciones pendientes",
            "groups": groups,
            "count": sum(len(g["items"]) for g in groups),
        },
    )
