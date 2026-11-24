import re

from django.core.exceptions import ValidationError
from django.core.validators import MinLengthValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def normalize_phone(value):
    if not value:
        return ""
    if not re.fullmatch(r"\+?[0-9 ()-]+", value):
        raise ValidationError(_("Ingresa un celular válido de 8 a 15 dígitos."))
    digits = re.sub(r"\D", "", value)
    if len(digits) == 10 and digits.startswith("3"):
        digits = "57" + digits
    if not 8 <= len(digits) <= 15:
        raise ValidationError(_("Ingresa un celular válido de 8 a 15 dígitos."))
    return "+" + digits


class ContactInquiry(models.Model):
    class Topic(models.TextChoices):
        PIECE = "piece", "Una pieza"
        CUSTOM = "custom", "Personalización"
        APPOINTMENT = "appointment", "Cita en el atelier"
        ORDER = "order", "Un pedido"
        OTHER = "other", "Otro"

    name = models.CharField(_("Nombre"), max_length=120)
    email = models.EmailField(_("Correo"))
    phone = models.CharField(_("Celular"), max_length=30, blank=True)
    topic = models.CharField(_("Motivo"), max_length=20, choices=Topic.choices)
    piece_sku = models.CharField(_("SKU de la pieza"), max_length=64, blank=True)
    message = models.TextField(
        _("Mensaje"),
        validators=[
            MinLengthValidator(20),
        ],
        max_length=2000,
    )
    preferred_channel = models.CharField(
        _("Canal preferido"), max_length=10, choices=[("email", "Correo"), ("whatsapp", "WhatsApp")]
    )
    privacy_version = models.PositiveIntegerField(_("Versión de privacidad"))
    locale = models.CharField(
        _("Idioma"), max_length=2, choices=[("es", "Español"), ("en", "Inglés")]
    )
    status = models.CharField(
        _("Estado"),
        max_length=10,
        choices=[("new", "Nuevo"), ("answered", "Respondido"), ("archived", "Archivado")],
        default="new",
    )
    created_at = models.DateTimeField(_("Fecha"), auto_now_add=True)
    answered_at = models.DateTimeField(_("Respondido el"), null=True, blank=True)

    class Meta:
        verbose_name = "Mensaje de contacto"
        verbose_name_plural = "Mensajes de contacto"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} — {self.get_topic_display()}"

    def save(self, *args, **kwargs):
        self.phone = normalize_phone(self.phone)
        if self.status == "answered" and not self.answered_at:
            self.answered_at = timezone.now()
        elif self.status == "new":
            self.answered_at = None
        if kwargs.get("update_fields") is not None:
            fields = set(kwargs["update_fields"])
            if "status" in fields:
                fields.add("answered_at")
            if "phone" in fields:
                fields.add("phone")
            kwargs["update_fields"] = fields
        super().save(*args, **kwargs)
