from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, cast

from django.contrib import admin
from django.contrib.admin.options import IncorrectLookupParameters
from django.db.models import Exists, OuterRef
from django.utils.dateparse import parse_date
from unfold.contrib.filters.admin import RangeDateFilter, RangeNumericFilter

from apps.core.formatting import BOGOTA

if TYPE_CHECKING:

    class _FilterBase(admin.FieldListFilter):
        parameter_name: str

        def __init__(self, *args, **kwargs): ...

    _DateFilterBase = _FilterBase
    _NumericFilterBase = _FilterBase
else:
    _DateFilterBase = RangeDateFilter
    _NumericFilterBase = RangeNumericFilter


class OrderDateFilter(_DateFilterBase):
    """Include both calendar dates, in the shop's timezone."""

    def queryset(self, request, queryset):
        try:
            for suffix, lookup in (("from", "gte"), ("to", "lt")):
                raw = cast(str, self.used_parameters.get(f"{self.parameter_name}_{suffix}"))
                if not raw:
                    continue
                day = parse_date(raw)
                if day is None:
                    raise ValueError
                if suffix == "to":
                    day += timedelta(days=1)
                queryset = queryset.filter(
                    **{
                        f"{self.parameter_name}__{lookup}": datetime.combine(
                            day, time.min, tzinfo=BOGOTA
                        ),
                    }
                )
            return queryset
        except (ValueError, TypeError) as exc:
            raise IncorrectLookupParameters("Selecciona fechas válidas.") from exc


class OrderTotalFilter(_NumericFilterBase):
    """Show pesos to the owner; storage remains in cents."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title = "Total (pesos colombianos)"

    def queryset(self, request, queryset):
        try:
            for suffix, lookup in (("from", "gte"), ("to", "lte")):
                value = cast(str, self.used_parameters.get(f"{self.parameter_name}_{suffix}"))
                if value in (None, ""):
                    continue
                amount = Decimal(value)
                if not amount.is_finite() or amount < 0:
                    raise ValueError
                queryset = queryset.filter(**{f"{self.parameter_name}__{lookup}": amount * 100})
            return queryset
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise IncorrectLookupParameters("Indica un total válido en pesos.") from exc


class CenterFilter(admin.SimpleListFilter):
    title = "Centro de pedidos"
    parameter_name = "center"

    def lookups(self, request, model_admin):
        return (
            ("pending", "Pendientes"),
            ("attention", "Requieren atención"),
            ("unpaid", "Por pagar"),
            ("paid", "Cobros aprobados"),
            ("prepare", "Por preparar"),
            ("incidents", "Incidencias abiertas"),
        )

    def queryset(self, request, queryset):
        from .metrics import collection_window
        from .models import OrderIncident

        incidents = OrderIncident.objects.filter(order_id=OuterRef("pk"), status="open")
        if self.value() == "pending":
            return queryset.exclude(fulfillment_status__in=["delivered", "cancelled", "returned"])
        if self.value() == "attention":
            return queryset.filter(needs_attention=True)
        if self.value() == "unpaid":
            return queryset.filter(payment_status__in=["pending", "awaiting_manual_payment"])
        if self.value() == "paid":
            start, end = collection_window(request.GET.get("period", "today"))
            return queryset.filter(payment_status="approved", paid_at__gte=start, paid_at__lte=end)
        if self.value() == "prepare":
            return queryset.filter(
                payment_status="approved", fulfillment_status="unfulfilled"
            ).filter(~Exists(incidents.filter(blocking=True)))
        if self.value() == "incidents":
            return queryset.filter(Exists(incidents))
        return queryset


class PeriodFilter(admin.SimpleListFilter):
    title = "Período de cobros"
    parameter_name = "period"

    def lookups(self, request, model_admin):
        return (
            ("today", "Hoy"),
            ("seven_days", "7 días"),
            ("thirty_days", "30 días"),
            ("month", "Mes actual"),
        )

    def queryset(self, request, queryset):
        return queryset
