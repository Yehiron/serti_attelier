from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpRequest
from django.urls import URLPattern, path, reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from apps.orders.admin import ReadOnlyInline

from .models import PaymentAttempt, PaymentEvent


class AttemptInline(ReadOnlyInline):
    model = PaymentAttempt
    fields = (
        "reference",
        "status",
        "amount_cents",
        "payment_method_type",
        "provider_transaction_id",
    )
    readonly_fields = fields


class EventInline(ReadOnlyInline):
    model = PaymentEvent
    fields = ("status", "outcome", "source", "received_at")
    readonly_fields = fields


class OrderEventInline(EventInline):
    fk_name = "order"


class ReadOnlyAdmin(ModelAdmin):  # type: ignore[misc]
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(ReadOnlyAdmin):
    list_display = ("reference", "channel", "status", "amount_cents")
    readonly_fields = (
        *(f.name for f in PaymentAttempt._meta.fields if f.name != "manual_proof"),
        "proof_download",
    )
    exclude = ("manual_proof",)
    inlines = (EventInline,)

    @admin.display(description="Soporte privado")
    def proof_download(self, obj: PaymentAttempt) -> str:
        if not obj.manual_proof:
            return "—"
        return format_html(
            '<a href="{}">Descargar soporte</a>', reverse("admin:payments-proof", args=[obj.pk])
        )

    def get_urls(self) -> list[URLPattern]:
        return [
            path(
                "<int:pk>/proof/", self.admin_site.admin_view(self.download), name="payments-proof"
            ),
            *super().get_urls(),
        ]

    def download(self, request: HttpRequest, pk: int) -> FileResponse:
        if not request.user.has_perm("payments.view_paymentattempt"):
            raise PermissionDenied
        attempt = PaymentAttempt.objects.filter(pk=pk).first()
        if not attempt or not attempt.manual_proof:
            raise Http404
        try:
            response = FileResponse(
                attempt.manual_proof.open("rb"),
                as_attachment=True,
                filename=(attempt.manual_proof.name or "soporte").rsplit("/", 1)[-1],
                content_type="application/octet-stream",
            )
        except FileNotFoundError as exc:
            raise Http404 from exc
        response["X-Content-Type-Options"] = "nosniff"
        return response


@admin.register(PaymentEvent)
class PaymentEventAdmin(ReadOnlyAdmin):
    list_display = ("provider_transaction_id", "status", "outcome", "source", "received_at")
    readonly_fields = tuple(f.name for f in PaymentEvent._meta.fields)
