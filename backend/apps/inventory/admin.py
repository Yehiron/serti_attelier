from django.contrib import admin

from apps.core.admin import ReadOnlyAdmin

from .models import PieceReservation, PieceStatusChange


@admin.register(PieceReservation)
class ReservationAdmin(ReadOnlyAdmin):
    list_display = ("piece", "kind", "status", "reference", "expires_at")
    list_filter = ("kind", "status")
    search_fields = ("piece__sku", "reference")


@admin.register(PieceStatusChange)
class StatusChangeAdmin(ReadOnlyAdmin):
    list_display = ("piece", "from_state", "to_state", "reason", "ref", "actor", "at")
    list_filter = ("reason",)
    search_fields = ("piece__sku", "ref")
