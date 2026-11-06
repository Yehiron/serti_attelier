"""Dashboard selectors. All windows use Colombia time and approved payments only."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, cast
from urllib.parse import urlencode

from django.core.cache import cache
from django.db.models import Count, Field, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import Piece
from apps.catalog.selectors import missing_english_translation
from apps.core.formatting import BOGOTA, format_admin_cop
from apps.promotions.models import CouponRedemption

from .models import Order, OrderItem

MONTHS_ES = (
    "ene.", "feb.", "mar.", "abr.", "may.", "jun.",
    "jul.", "ago.", "sep.", "oct.", "nov.", "dic.",
)  # fmt: skip


def month_start(now: datetime, offset: int = 0) -> datetime:
    index = now.year * 12 + now.month - 1 + offset
    return now.replace(
        year=index // 12, month=index % 12 + 1, day=1, hour=0, minute=0, second=0, microsecond=0
    )


def admin_link(model: str, filters: dict[str, Any]) -> str:
    return reverse(f"admin:{model}_changelist") + "?" + urlencode(filters)


def compute_metrics(now: datetime | None = None) -> dict[str, Any]:
    now = (now or timezone.now()).astimezone(BOGOTA)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    approved = Order.objects.filter(payment_status="approved", paid_at__lte=now)
    windows = [
        ("today", _("Hoy"), today),
        ("seven_days", _("Últimos 7 días"), today - timedelta(days=6)),
        ("thirty_days", _("Últimos 30 días"), today - timedelta(days=29)),
        ("month", _("Mes actual"), month_start(now)),
    ]
    expressions: dict[str, Any] = {}
    for key, _label, start in windows:
        expressions[f"{key}_count"] = Count("pk", filter=Q(paid_at__gte=start))
        expressions[f"{key}_total"] = Sum("total_cents", filter=Q(paid_at__gte=start), default=0)
    values = approved.aggregate(**expressions)
    sales = [
        {
            "key": key,
            "label": label,
            "count": values[f"{key}_count"],
            "total_cents": values[f"{key}_total"],
            "total": format_admin_cop(values[f"{key}_total"]),
        }
        for key, label, _start in windows
    ]
    groups = {}
    for field in ("payment_status", "fulfillment_status"):
        labels = dict(cast("Field[Any, Any]", Order._meta.get_field(field)).flatchoices)
        groups[field] = [
            {
                "label": labels.get(row[field], row[field]),
                "count": row["count"],
                "url": admin_link("orders_order", {field: row[field]}),
                "highlight": row[field] == "awaiting_manual_payment",
            }
            for row in Order.objects.values(field).annotate(count=Count("pk")).order_by(field)
        ]
    attention = Order.objects.filter(needs_attention=True).count()
    months = {
        row["month"].strftime("%Y-%m"): row
        for row in approved.filter(paid_at__gte=month_start(now, -5))
        .annotate(month=TruncMonth("paid_at", tzinfo=BOGOTA))
        .values("month")
        .annotate(count=Count("pk"), total=Sum("total_cents"))
    }
    monthly = []
    maximum = max((r["total"] for r in months.values()), default=0) or 1
    for offset in range(-5, 1):
        start = month_start(now, offset)
        key = start.strftime("%Y-%m")
        row = months.get(key, {"count": 0, "total": 0})
        monthly.append(
            {
                "label": f"{MONTHS_ES[start.month - 1]} {start.year}",
                "count": row["count"],
                "total": format_admin_cop(row["total"]),
                "width": row["total"] * 100 // maximum,
            }
        )
    start90 = today - timedelta(days=89)
    sold_items = OrderItem.objects.filter(
        order__payment_status="approved", order__paid_at__gte=start90, order__paid_at__lte=now
    )
    breakdowns = {}
    for key, field in (
        ("categories", "piece__category__name_es"),
        ("stones", "piece__stones__name_es"),
    ):
        breakdowns[key] = list(
            sold_items.values(field)
            .annotate(count=Count("pk", distinct=True))
            .order_by("-count", field)
        )
        for row in breakdowns[key]:
            row["label"] = row.pop(field) or str(_("Sin asignar"))
    start30 = today - timedelta(days=29)
    redemptions = CouponRedemption.objects.filter(
        created_at__gte=start30, created_at__lte=now, order__payment_status="approved"
    )
    discounts = redemptions.aggregate(
        count=Count("pk"), total=Sum("order__discount_cents", default=0)
    )
    discounts["formatted_total"] = format_admin_cop(discounts["total"])
    coupons = cast(
        list[dict[str, Any]],
        list(
            redemptions.values("coupon__code")
            .annotate(count=Count("pk"), total=Sum("order__discount_cents"))
            .order_by("-count", "coupon__code")[:10]
        ),
    )
    for coupon in coupons:
        coupon["label"] = coupon["coupon__code"]
        coupon["formatted_total"] = format_admin_cop(coupon["total"])
    health_specs: list[tuple[str, Any, dict[str, Any]]] = [
        (
            str(_("Publicadas disponibles")),
            Q(status="published", sale_state="available"),
            {"status__exact": "published", "sale_state__exact": "available"},
        ),
        (str(_("Reservadas ahora")), Q(sale_state="reserved"), {"sale_state__exact": "reserved"}),
        (str(_("Preventa")), Q(sale_state="preorder"), {"sale_state__exact": "preorder"}),
        (
            str(_("Vendidas en 30 días")),
            Q(sale_state="sold", sold_at__gte=start30, sold_at__lte=now),
            {
                "sale_state__exact": "sold",
                "sold_at__gte": start30.isoformat(),
                "sold_at__lte": now.isoformat(),
            },
        ),
        (
            str(_("Publicadas sin traducción inglesa")),
            missing_english_translation(),
            {"health": "missing_en"},
        ),
        (
            str(_("Imágenes con errores")),
            Q(images__processing_status="failed"),
            {"health": "failed_images"},
        ),
    ]
    counts = Piece.objects.aggregate(
        **{
            f"h{i}": Count("pk", filter=query, distinct=True)
            for i, (_label, query, _filters) in enumerate(health_specs)
        }
    )
    health = [
        {"label": label, "count": counts[f"h{i}"], "url": admin_link("catalog_piece", filters)}
        for i, (label, _query, filters) in enumerate(health_specs)
    ]
    return {
        "sales": sales,
        "groups": groups,
        "attention": attention,
        "attention_url": admin_link("orders_order", {"needs_attention__exact": "1"}),
        "monthly": monthly,
        "breakdowns": breakdowns,
        "discounts": discounts,
        "coupons": coupons,
        "health": health,
    }


def dashboard_callback(request: HttpRequest, context: dict[str, Any]) -> dict[str, Any]:
    links = []
    for label, permission, url, post in (
        (_("Agregar pieza"), "catalog.add_piece", reverse("admin:catalog_piece_add"), False),
        (
            _("Editar portada"),
            "cms.change_homesection",
            reverse("admin:cms_homesection_changelist"),
            False,
        ),
        (_("Publicar inicio"), "cms.publish_content", reverse("admin:cms-home-publish"), True),
        (
            _("Pedidos pendientes de pago"),
            "orders.view_order",
            admin_link("orders_order", {"payment_status__in": "pending,awaiting_manual_payment"}),
            False,
        ),
    ):
        if request.user.has_perm(permission):
            links.append({"label": label, "url": url, "post": post})
    context = {**context, "quick_links": links}
    if not request.user.has_perm("orders.view_order"):
        return context
    key = f"orders:dashboard:v2:{timezone.now().astimezone(BOGOTA).date().isoformat()}"
    metrics = cache.get(key)
    if metrics is None:
        metrics = compute_metrics()
        cache.set(key, metrics, 60)
    return {**context, "shop_metrics": metrics}


def collection_window(period, now=None):
    now = (now or timezone.now()).astimezone(BOGOTA)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = {
        "today": today,
        "seven_days": today - timedelta(days=6),
        "thirty_days": today - timedelta(days=29),
        "month": month_start(now),
    }
    return start.get(period, today), now


def order_center_metrics(period="today", now=None):
    from django.db.models import Exists, OuterRef

    from .models import OrderIncident

    start, end = collection_window(period, now)
    paid = Order.objects.filter(payment_status="approved", paid_at__gte=start, paid_at__lte=end)
    cancelled = Q(fulfillment_status__in=["cancelled", "returned"])
    amounts = paid.aggregate(
        count=Count("pk"),
        total=Sum("total_cents", default=0),
        cancelled_count=Count("pk", filter=cancelled),
        cancelled_total=Sum("total_cents", filter=cancelled, default=0),
    )
    blocking = OrderIncident.objects.filter(order_id=OuterRef("pk"), status="open", blocking=True)
    open_incidents = OrderIncident.objects.filter(status="open")
    incident_counts = open_incidents.aggregate(
        count=Count("pk"), payment=Count("pk", filter=~Q(kind="other"))
    )
    counts = Order.objects.annotate(blocked=Exists(blocking)).aggregate(
        prepare=Count(
            "pk",
            filter=Q(payment_status="approved", fulfillment_status="unfulfilled", blocked=False),
        ),
        manual=Count("pk", filter=Q(payment_status="awaiting_manual_payment")),
    )
    return [
        {
            "label": "Cobros aprobados",
            "count": amounts["count"],
            "amount": format_admin_cop(amounts["total"]),
            "cancelled_count": amounts["cancelled_count"],
            "cancelled_amount": format_admin_cop(amounts["cancelled_total"]),
            "url": admin_link("orders_order", {"center": "paid", "period": period}),
        },
        {
            "label": "Por preparar",
            "count": counts["prepare"],
            "url": admin_link("orders_order", {"center": "prepare"}),
        },
        {
            "label": "Pagos manuales por confirmar",
            "count": counts["manual"],
            "url": admin_link("orders_order", {"payment_status__exact": "awaiting_manual_payment"}),
        },
        {
            "label": "Incidencias abiertas",
            "count": incident_counts["count"],
            "payment_count": incident_counts["payment"],
            "url": admin_link("orders_order", {"center": "incidents"}),
        },
    ]
