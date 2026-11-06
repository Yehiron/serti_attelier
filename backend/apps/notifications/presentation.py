"""Safe labels for the order card; never display provider exception bodies."""

from apps.promotions.services import email_digest

from .models import EVENT_LABELS, STATUS_LABELS
from .services import can_resend, masked_recipient, recipient_for

ERROR_LABELS = {
    "whatsapp_simulation": "Simulación",
    "recipient_changed": "El destinatario cambió; requiere revisión",
    "order_unavailable": "Pedido no disponible",
    "email_recipient_unconfigured": "Correo sin configurar",
    "email_smtp_unconfigured": "Servidor de correo sin configurar",
    "whatsapp_provider_unconfigured": "Proveedor de WhatsApp sin configurar",
    "whatsapp_unconfigured": "WhatsApp sin configurar",
    "whatsapp_configuration_invalid": "Configuración de WhatsApp incompleta",
}


def communication_rows(order, *, can_manage):
    rows = []
    for delivery in order.deliveries.order_by("created_at", "pk"):
        recipient = delivery.payload.get("recipient_label")
        if not recipient:
            current = recipient_for(order, delivery.channel, delivery.audience)
            recipient = (
                masked_recipient(current, delivery.channel)
                if email_digest(current) == delivery.recipient_hash
                else "Destinatario anterior no recuperable"
            )
        audience = "Cliente" if delivery.audience == "customer" else "SERTI"
        rows.append(
            {
                "delivery": delivery,
                "event": EVENT_LABELS.get(delivery.event, "Comunicación del pedido"),
                "channel": "Correo" if delivery.channel == "email" else "WhatsApp",
                "recipient": f"{audience} · {recipient}",
                "status": STATUS_LABELS.get(delivery.status, "Pendiente de revisión"),
                "error": ERROR_LABELS.get(
                    delivery.last_error, "No se pudo enviar; revisa la configuración"
                )
                if delivery.last_error
                else "",
                "reconstructed": delivery.status == "sent" and not delivery.payload.get("rendered"),
                "can_resend": can_manage and can_resend(delivery),
                "can_copy": can_manage
                and delivery.status == "sent"
                and delivery.channel == "email"
                and delivery.audience == "customer"
                and order.deliveries.filter(
                    idempotency_key__startswith=delivery.idempotency_key.split(":copy:", 1)[0]
                    + ":copy:"
                ).count()
                < 3,
            }
        )
    return rows
