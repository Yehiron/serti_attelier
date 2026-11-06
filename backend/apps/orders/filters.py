from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.admin.views.main import IncorrectLookupParameters
from django.utils.dateparse import parse_date
from unfold.contrib.filters.admin import RangeDateFilter, RangeNumericFilter

from apps.core.formatting import BOGOTA


class OrderDateFilter(RangeDateFilter):
    """Include both calendar dates, in the shop's timezone."""

    def queryset(self, request, queryset):
        try:
            for suffix, lookup in (("from", "gte"), ("to", "lt")):
                raw = self.used_parameters.get(f"{self.parameter_name}_{suffix}")
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


class OrderTotalFilter(RangeNumericFilter):
    """Show pesos to the owner; storage remains in cents."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title = "Total (pesos colombianos)"

    def queryset(self, request, queryset):
        try:
            for suffix, lookup in (("from", "gte"), ("to", "lte")):
                value = self.used_parameters.get(f"{self.parameter_name}_{suffix}")
                if value in (None, ""):
                    continue
                amount = Decimal(value)
                if not amount.is_finite() or amount < 0:
                    raise ValueError
                queryset = queryset.filter(**{f"{self.parameter_name}__{lookup}": amount * 100})
            return queryset
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise IncorrectLookupParameters("Indica un total válido en pesos.") from exc
