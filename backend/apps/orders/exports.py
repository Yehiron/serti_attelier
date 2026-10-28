from __future__ import annotations

import csv

from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse

from apps.audit.services import record
from apps.core.formatting import format_bogota_datetime, place_name

from .models import Order

# Spanish headers and Excel-friendly format for SERTI (Colombian Excel uses ";" as the
# list separator and needs a UTF-8 BOM to show accents). Amounts are whole pesos.
COLUMNS = (
    "Pedido",
    "Fecha",
    "Cliente",
    "Correo",
    "Celular",
    "Municipio",
    "Departamento",
    "Piezas (SKU)",
    "Subtotal (COP)",
    "Descuento (COP)",
    "Certificado (COP)",
    "Total (COP)",
    "Estado del pago",
    "Estado del envío",
    "Pagado el",
)


def pesos(cents: int) -> str:
    whole, rest = divmod(cents, 100)
    return f"{whole},{rest:02d}" if rest else str(whole)


def safe_cell(value: object) -> str:
    text = str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text


def export_orders(queryset: QuerySet[Order], *, request: HttpRequest) -> HttpResponse:
    if not request.user.has_perm("orders.export_orders"):
        raise PermissionDenied
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="pedidos.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(COLUMNS)
    for order in queryset.select_related("shipping_municipality__department").prefetch_related(
        "items"
    ):
        place = order.shipping_municipality
        writer.writerow(
            map(
                safe_cell,
                (
                    order.number,
                    format_bogota_datetime(order.created_at, "es"),
                    order.customer_name,
                    order.customer_email,
                    order.customer_phone,
                    place_name(place.name),
                    place_name(place.department.name),
                    ", ".join(item.sku for item in order.items.all()),
                    pesos(order.subtotal_cents),
                    pesos(order.discount_cents),
                    pesos(order.certificate_cents),
                    pesos(order.total_cents),
                    order.get_payment_status_display(),
                    order.get_fulfillment_status_display(),
                    format_bogota_datetime(order.paid_at, "es") if order.paid_at else "",
                ),
            )
        )
        record("orders.exported", actor=request.user, obj=order, request=request)
    return response
