import contextlib
import re
from copy import copy
from typing import TYPE_CHECKING, Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Avg, F
from django.http import HttpResponseBadRequest, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from apps.audit.services import record

from .models import ContactInquiry, normalize_phone

if TYPE_CHECKING:
    _InquiryAdminBase = admin.ModelAdmin[ContactInquiry]
else:
    _InquiryAdminBase = ModelAdmin


@admin.register(ContactInquiry)
class ContactInquiryAdmin(_InquiryAdminBase):
    change_list_template = "admin/inquiries/contactinquiry/change_list.html"

    def get_urls(self):
        return [
            path(
                "<int:object_id>/status/",
                self.admin_site.admin_view(self.status_view),
                name="inquiries_contactinquiry_status",
            ),
            *super().get_urls(),
        ]

    def status_view(self, request, object_id):
        if request.method != "POST":
            from django.http import HttpResponseNotAllowed

            return HttpResponseNotAllowed(["POST"])
        obj = get_object_or_404(self.get_queryset(request), pk=object_id)
        if not self.has_change_permission(request, obj):
            return HttpResponseForbidden()
        target = request.POST.get("target")
        if target not in {"new", "answered", "archived"}:
            return HttpResponseBadRequest()
        self._set_status(request, self.get_queryset(request).filter(pk=obj.pk), target)
        query = request.GET.copy()
        query["mensaje"] = obj.pk
        return HttpResponseRedirect(
            reverse("admin:inquiries_contactinquiry_changelist") + "?" + query.urlencode()
        )

    def changelist_view(self, request, extra_context=None):
        clean = copy(request)
        clean.GET = request.GET.copy()
        clean.GET.pop("mensaje", None)
        filter_key = clean.GET.pop("bandeja", [None])[-1]
        base = self.get_queryset(request)
        # Counts follow the search term, independently of the selected chip.
        search = request.GET.get("q", "")
        searched, _ = self.get_search_results(request, base, search)
        specs = [
            ("new", "Sin responder", {"status": "new"}),
            ("answered", "Respondidos", {"status": "answered"}),
            ("archived", "Archivados", {"status": "archived"}),
            ("piece", "Sobre una pieza", {"topic": "piece"}),
            ("custom", "Personalización", {"topic": "custom"}),
            ("all", "Todos", {}),
        ]
        if filter_key not in {item[0] for item in specs}:
            filter_key = "new" if searched.filter(status="new").exists() else "all"
        chosen = next(item[2] for item in specs if item[0] == filter_key)
        for key, value in chosen.items():
            clean.GET[key + "__exact"] = value
        response = super().changelist_view(clean, extra_context)
        if not isinstance(response, TemplateResponse) or "cl" not in (response.context_data or {}):
            return response
        context: dict[str, Any] = response.context_data or {}
        cl = context["cl"]
        rows = list(cl.result_list)
        selected = next((x for x in rows if str(x.pk) == request.GET.get("mensaje")), None)
        if selected is None and request.GET.get("mensaje", "").isdigit():
            selected = cl.queryset.filter(pk=int(request.GET["mensaje"])).first()
        selected = selected or (rows[0] if rows else None)

        def query_url(**changes):
            query = request.GET.copy()
            for key, value in changes.items():
                if value is None:
                    query.pop(key, None)
                else:
                    query[key] = str(value)
            return "?" + query.urlencode()

        tabs = [
            {
                "label": label,
                "count": searched.filter(**criteria).count(),
                "active": key == filter_key,
                "url": query_url(bandeja=key, mensaje=None, p=None),
            }
            for key, label, criteria in specs
        ]
        from apps.catalog.models import Piece

        piece = (
            Piece.objects.filter(sku=selected.piece_sku).first()
            if selected and selected.piece_sku
            else None
        )
        image = piece.images.order_by("-is_primary", "position").first() if piece else None
        number = ""
        if selected and selected.phone:
            with contextlib.suppress(ValidationError):
                number = re.sub(r"\D", "", normalize_phone(selected.phone))
        average = base.filter(status="answered", answered_at__isnull=False).aggregate(
            value=Avg(F("answered_at") - F("created_at"))
        )["value"]
        average_text = None
        if average is not None:
            minutes = max(0, round(average.total_seconds() / 60))
            average_text = (
                f"{minutes // 60} h {minutes % 60} min" if minutes >= 60 else f"{minutes} min"
            )
        context.update(
            request=request,
            msg_tabs=tabs,
            msg_filter=filter_key,
            msg_rows=[
                {
                    "obj": x,
                    "initials": "".join(part[0].upper() for part in x.name.split()[:2]),
                    "url": query_url(mensaje=x.pk),
                }
                for x in rows
            ],
            selected=selected,
            mobile_detail=bool(request.GET.get("mensaje")),
            back_url=query_url(mensaje=None),
            status_url=(
                reverse("admin:inquiries_contactinquiry_status", args=[selected.pk])
                + "?"
                + request.GET.urlencode()
            )
            if selected
            else "",
            can_change=bool(selected and self.has_change_permission(request, selected)),
            spam=looks_like_spam(selected.message) if selected else False,
            bogota_date=timezone.localtime(selected.created_at, ZoneInfo("America/Bogota"))
            if selected
            else None,
            piece=piece,
            piece_image=image.original.url if image and image.original else "",
            piece_admin_url=reverse("admin:catalog_piece_change", args=[piece.pk]) if piece else "",
            piece_store_url=f"/es/piezas/{piece.slug_es}" if piece and piece.slug_es else "",
            reply_data={
                "name": selected.name,
                "piece": piece.name_es if piece else "",
                "locale": selected.locale,
                "phone": number,
                "email": selected.email,
                "topic": str(selected.get_topic_display()),
            }
            if selected
            else {},
            new_count=base.filter(status="new").count(),
            average_text=average_text,
            previous_url=query_url(p=cl.page_num - 1, mensaje=None) if cl.page_num > 1 else "",
            next_url=query_url(p=cl.page_num + 1, mensaje=None)
            if cl.page_num < cl.paginator.num_pages
            else "",
            page_number=cl.page_num,
            page_total=cl.paginator.num_pages,
        )
        return response

    list_display = ("created_at", "name", "topic", "preferred_channel", "status")
    list_filter = ("status", "topic")
    search_fields = ("name", "email")
    readonly_fields = (
        "name",
        "email",
        "phone",
        "topic",
        "piece_sku",
        "message",
        "preferred_channel",
        "privacy_version",
        "locale",
        "created_at",
        "answered_at",
        "reply_links",
    )
    fields = (*readonly_fields, "status")
    actions = ("mark_answered", "archive")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Responder")
    def reply_links(self, obj):
        try:
            number = re.sub(r"\D", "", normalize_phone(obj.phone)) if obj.phone else ""
        except ValidationError:
            number = ""
        wa = (
            format_html(
                '<a href="https://wa.me/{}" target="_blank" rel="noopener noreferrer">'
                "Responder por WhatsApp</a> · ",
                number,
            )
            if number
            else ""
        )
        return format_html(
            '{}<a href="mailto:{}">Responder por correo</a>', wa, quote(obj.email, safe="@")
        )

    def _record_status(self, request, obj, previous):
        if previous == obj.status:
            return
        action = {"answered": "inquiries.answered", "archived": "inquiries.archived"}.get(
            obj.status, "inquiries.status_changed"
        )
        record(
            action,
            actor=request.user,
            obj=obj,
            diff={"status": [previous, obj.status]},
            request=request,
        )

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        previous = (
            ContactInquiry.objects.select_for_update().get(pk=obj.pk).status if change else None
        )
        super().save_model(request, obj, form, change)
        if previous is not None:
            self._record_status(request, obj, previous)

    @transaction.atomic
    def _set_status(self, request, queryset, status):
        for obj in queryset.select_for_update():
            previous = obj.status
            if previous != status:
                obj.status = status
                obj.save(update_fields=["status"])
                self._record_status(request, obj, previous)

    @admin.action(description="Marcar como respondido")
    def mark_answered(self, request, queryset):
        self._set_status(request, queryset, "answered")

    @admin.action(description="Archivar")
    def archive(self, request, queryset):
        self._set_status(request, queryset, "archived")


# The inbox keeps Django's changelist for permissions, search, pagination and bulk actions.
def looks_like_spam(message):
    """Flag long unbroken text, dominant repeated letters, or long text without vowels.

    Short messages are excluded from the vowel rule to avoid flagging greetings or acronyms.
    This is a visual hint only; it never changes a message's status.
    """
    from collections import Counter

    text = message.strip()
    letters = [c.lower() for c in text if c.isalpha()]
    return bool(
        (len(text) > 15 and not any(c.isspace() for c in text))
        or (len(letters) > 15 and Counter(letters).most_common(1)[0][1] / len(letters) > 0.6)
        or (len(letters) > 15 and not any(c in "aeiouáéíóúü" for c in letters))
    )
