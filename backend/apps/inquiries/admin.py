import re
from urllib.parse import quote

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from apps.audit.services import record

from .models import ContactInquiry, normalize_phone


@admin.register(ContactInquiry)
class ContactInquiryAdmin(ModelAdmin):
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
