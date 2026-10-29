from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.validators import MinValueValidator, RegexValidator, URLValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from modeltranslation.manager import MultilingualManager


def validate_https(value: str) -> None:
    URLValidator(schemes=["https"])(value)


class Department(models.Model):
    code = models.CharField(verbose_name=_("Código"), max_length=2, primary_key=True)
    name = models.CharField(verbose_name=_("Nombre"), max_length=100)

    class Meta:
        verbose_name = _("departamento")
        verbose_name_plural = _("departamentos")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Municipality(models.Model):
    code = models.CharField(verbose_name=_("Código"), max_length=5, primary_key=True)
    name = models.CharField(verbose_name=_("Nombre"), max_length=100)
    department = models.ForeignKey(
        Department,
        verbose_name=_("Departamento"),
        on_delete=models.PROTECT,
        related_name="municipalities",
    )
    kind = models.CharField(verbose_name=_("Tipo"), max_length=80)

    class Meta:
        verbose_name = _("municipio")
        verbose_name_plural = _("municipios")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class SiteSettings(models.Model):
    if TYPE_CHECKING:
        whatsapp_general_en: str
        manual_payment_instructions_en: str

    objects: MultilingualManager[SiteSettings] = MultilingualManager()
    id = models.PositiveSmallIntegerField(
        verbose_name=_("ID"), primary_key=True, default=1, editable=False
    )
    whatsapp_number = models.CharField(
        verbose_name=_("Número de WhatsApp"),
        max_length=15,
        blank=True,
        validators=[RegexValidator(r"^[1-9][0-9]{1,14}$", _("Usa dígitos E.164 sin el signo +."))],
    )
    instagram_url = models.URLField(
        verbose_name=_("Enlace de Instagram"), blank=True, validators=[validate_https]
    )
    facebook_url = models.URLField(
        verbose_name=_("Enlace de Facebook"), blank=True, validators=[validate_https]
    )
    tiktok_url = models.URLField(
        verbose_name=_("Enlace de TikTok"), blank=True, validators=[validate_https]
    )
    pinterest_url = models.URLField(
        verbose_name=_("Enlace de Pinterest"), blank=True, validators=[validate_https]
    )
    support_email = models.EmailField(verbose_name=_("Correo de atención"), blank=True)
    whatsapp_general = models.TextField(
        verbose_name=_("Mensaje de consulta general"),
        default="Hola SERTI, quisiera información sobre {name} ({sku}). {url}",
    )
    whatsapp_preorder = models.TextField(
        verbose_name=_("Mensaje de preventa"),
        default="Hola SERTI, me interesa la preventa de {name} ({sku}). {url}",
    )
    whatsapp_reserved = models.TextField(
        verbose_name=_("Mensaje de pieza reservada"),
        default="Hola SERTI, quisiera saber si {name} ({sku}) vuelve a estar disponible. {url}",
    )
    whatsapp_sold = models.TextField(
        verbose_name=_("Mensaje de pieza vendida"),
        default=(
            "Hola SERTI, me enamoré de {name} ({sku}) y quisiera "
            "una pieza única inspirada en ella. {url}"
        ),
    )
    certificate_price_cents = models.PositiveBigIntegerField(
        verbose_name=_("Precio del certificado (centavos)"), default=0
    )
    manual_payment_instructions = models.TextField(
        verbose_name=_("Instrucciones de pago manual"),
        default=(
            "SERTI compartirá los datos de Efecty o transferencia por WhatsApp. "
            "Pedido {number}, total {total}. Paga antes de {deadline}."
        ),
    )
    online_reservation_minutes = models.PositiveIntegerField(
        verbose_name=_("Duración de reserva en línea (minutos)"),
        default=30,
        validators=[MinValueValidator(1)],
    )
    manual_reservation_hours = models.PositiveIntegerField(
        verbose_name=_("Duración de reserva manual (horas)"),
        default=24,
        validators=[MinValueValidator(1)],
    )

    class Meta:
        verbose_name = _("configuración del sitio")
        verbose_name_plural = _("configuración del sitio")
        constraints = [
            models.CheckConstraint(condition=models.Q(pk=1), name="site_settings_singleton"),
            models.CheckConstraint(
                condition=models.Q(
                    online_reservation_minutes__gt=0, manual_reservation_hours__gt=0
                ),
                name="positive_reservation_durations",
            ),
        ]

    def __str__(self) -> str:
        return str(_("Configuración del sitio"))

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.pk = 1
        super().save(*args, **kwargs)
