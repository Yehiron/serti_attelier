"""Private panel notices, durable and deduplicated inside the caller's transaction."""

from django.contrib.auth.backends import ModelBackend
from django.db import transaction
from django.db.models import Q
from django.urls import reverse

from apps.core.formatting import format_admin_cop

from .models import AdminNotification, AdminNotificationReceipt


@transaction.atomic
def publish(order, kind, key, *, payment_only=False):
    notice, created = AdminNotification.objects.get_or_create(
        event_key=key,
        defaults={
            "order": order,
            "kind": kind,
            "message": str(AdminNotification.Kind(kind).label),
            "payment_only": payment_only,
        },
    )
    if created:
        backend = ModelBackend()
        users = backend.with_perm("orders.view_order").filter(is_staff=True)
        if payment_only:
            users = users.filter(pk__in=backend.with_perm("orders.resolve_payment_incident"))
        AdminNotificationReceipt.objects.bulk_create(
            [
                AdminNotificationReceipt(notification=notice, user_id=pk)
                for pk in users.values_list("pk", flat=True)
            ]
        )
    return notice


def visible_receipts(user):
    # One permissions query rather than has_perm's separate direct/group queries.
    if not user.is_authenticated or not user.is_active or not user.is_staff:
        return None
    if user.is_superuser:
        permissions = {"view_order", "resolve_payment_incident"}
    else:
        from django.contrib.auth.models import Permission

        permissions = set(
            Permission.objects.filter(
                Q(user=user) | Q(group__user=user),
                content_type__app_label="orders",
                codename__in=["view_order", "resolve_payment_incident"],
            ).values_list("codename", flat=True)
        )
    if "view_order" not in permissions:
        return None
    rows = AdminNotificationReceipt.objects.filter(user=user)
    if "resolve_payment_incident" not in permissions:
        rows = rows.filter(notification__payment_only=False)
    return rows


def serialize_receipt(row):
    notice = row.notification
    order = notice.order
    return {
        "id": notice.pk,
        "message": notice.message,
        "number": order.number,
        "amount": format_admin_cop(order.total_cents) if notice.kind == "paid" else None,
        "created_at": notice.created_at.isoformat(),
        "read": row.read_at is not None,
        "url": reverse("admin:orders_order_change", args=[order.pk]),
    }


def unread_data(user, since=0):
    rows = visible_receipts(user)
    if rows is None:
        return None
    unread = rows.filter(read_at__isnull=True)
    count = unread.count()
    latest = list(
        rows.select_related("notification__order")
        .only(
            "read_at",
            "notification__message",
            "notification__kind",
            "notification__created_at",
            "notification__order__number",
            "notification__order__total_cents",
        )
        .order_by("-notification_id")[:20]
    )
    return {
        "count": count,
        "items": [serialize_receipt(row) for row in latest],
        "new": [
            serialize_receipt(row)
            for row in latest
            if row.notification_id > since and row.read_at is None
        ],
    }
