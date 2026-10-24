from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from modeltranslation.manager import MultilingualManager


class Department(models.Model):
    code = models.CharField(max_length=2, primary_key=True)
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["name"]
        verbose_name = _("departamento")

    def __str__(self) -> str:
        return self.name


class Municipality(models.Model):
    code = models.CharField(max_length=5, primary_key=True)
    name = models.CharField(max_length=100)
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="municipalities"
    )
    kind = models.CharField(max_length=80)

    class Meta:
        ordering = ["name"]
        verbose_name = _("municipio")

    def __str__(self) -> str:
        return self.name


class SiteSettings(models.Model):
    if TYPE_CHECKING:
        whatsapp_general_en: str

    objects: MultilingualManager[SiteSettings] = MultilingualManager()
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    whatsapp_number = models.CharField(
        max_length=15,
        blank=True,
        validators=[RegexValidator(r"^[1-9][0-9]{1,14}$", _("Usa dígitos E.164 sin el signo +."))],
    )
    whatsapp_general = models.TextField(
        default="Hola SERTI, quisiera información sobre {name} ({sku}). {url}"
    )
    whatsapp_preorder = models.TextField(
        default="Hola SERTI, me interesa la preventa de {name} ({sku}). {url}"
    )
    whatsapp_reserved = models.TextField(
        default="Hola SERTI, quisiera saber si {name} ({sku}) vuelve a estar disponible. {url}"
    )
    whatsapp_sold = models.TextField(
        default=(
            "Hola SERTI, me enamoré de {name} ({sku}) y quisiera "
            "una pieza única inspirada en ella. {url}"
        )
    )
    online_reservation_minutes = models.PositiveIntegerField(
        default=30, validators=[MinValueValidator(1)]
    )
    manual_reservation_hours = models.PositiveIntegerField(
        default=24, validators=[MinValueValidator(1)]
    )

    class Meta:
        verbose_name = _("configuración del sitio")
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
