"""Incident writes serialize on the order, including the derived attention flag."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.services import record

from .models import Order, OrderIncident


@transaction.atomic
def open_incident(order, kind, *, detail="", actor=None, blocking=True, notify=True):
    order = Order.objects.select_for_update(of=("self",)).get(pk=order.pk)
    if kind not in OrderIncident.Kind.values:
        raise ValidationError("Selecciona un tipo de incidencia válido.")
    incident, created = OrderIncident.objects.get_or_create(
        order=order,
        kind=kind,
        status="open",
        defaults={"detail": detail, "blocking": blocking, "created_by": actor},
    )
    Order.objects.filter(pk=order.pk).update(needs_attention=True)
    if created:
        from apps.notifications.panel import publish

        publish(
            order,
            "incident",
            f"incident:{incident.pk}",
            payment_only=kind != OrderIncident.Kind.OTHER,
        )
        record("orders.incident_opened", obj=incident, actor=actor)
        if notify:
            from .events import _notify

            _notify(
                order.pk,
                "needs_attention",
                event_key=f"incident:{incident.pk}",
                metadata={"incident_kind": incident.kind},
            )
        if kind in {OrderIncident.Kind.NO_PIECE, OrderIncident.Kind.CANCELLED_PAYMENT}:
            from .events import _notify

            _notify(order.pk, "payment_issue", event_key=f"incident:{incident.pk}")
    return incident


@transaction.atomic
def open_manual_incident(order, *, actor, detail, blocking=True):
    if not actor.has_perm("orders.add_orderincident"):
        raise PermissionDenied
    detail = detail.strip()
    if len(detail) < 5 or len(detail) > 2000:
        raise ValidationError(
            "Describe la incidencia con entre 5 y 2000 caracteres, sin datos de tarjeta."
        )
    return open_incident(
        order, OrderIncident.Kind.OTHER, actor=actor, detail=detail, blocking=blocking
    )


@transaction.atomic
def resolve_incident(incident, *, actor, note, notify=False):
    order = Order.objects.select_for_update(of=("self",)).get(pk=incident.order_id)
    incident = OrderIncident.objects.select_for_update(of=("self",)).get(pk=incident.pk)
    if not actor.has_perm(incident.resolution_permission):
        raise PermissionDenied
    note = note.strip()
    if len(note) < 5 or len(note) > 2000:
        raise ValidationError("Escribe una nota de resolución de entre 5 y 2000 caracteres.")
    if incident.status != "open":
        raise ValidationError("La incidencia ya fue resuelta. Recarga el pedido.")
    incident.status = "resolved"
    incident.resolved_by = actor
    incident.resolved_at = timezone.now()
    incident.resolution_note = note
    incident.save(update_fields=["status", "resolved_by", "resolved_at", "resolution_note"])
    Order.objects.filter(pk=order.pk).update(
        needs_attention=order.incidents.filter(status="open").exists()
    )
    record("orders.incident_resolved", obj=incident, actor=actor)
    if notify:
        from .events import _notify

        _notify(
            order.pk,
            "incident_resolved",
            event_key=f"incident:{incident.pk}:resolved",
            metadata={"incident_kind": incident.kind},
        )
    return incident
