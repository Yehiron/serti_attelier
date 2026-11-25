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
        whatsapp_general_es: str
        manual_payment_instructions_es: str
        whatsapp_general_en: str
        manual_payment_instructions_en: str

    objects: MultilingualManager[SiteSettings] = MultilingualManager()
    id = models.PositiveSmallIntegerField(
        verbose_name=_("ID"), primary_key=True, default=1, editable=False
    )

    class TypeScale(models.IntegerChoices):
        SMALL = 90, _("Pequeño 90 %")
        NORMAL = 100, _("Normal 100 %")
        LARGE = 110, _("Grande 110 %")
        EXTRA_LARGE = 120, _("Muy grande 120 %")

    title_scale = models.PositiveSmallIntegerField(
        verbose_name=_("Tamaño de los títulos"),
        choices=TypeScale,
        default=TypeScale.NORMAL,
        help_text=_(
            "Ajusta los títulos de toda la tienda, también en celular. Normal equivale al 100 %."
        ),
    )
    text_scale = models.PositiveSmallIntegerField(
        verbose_name=_("Tamaño del texto"),
        choices=TypeScale,
        default=TypeScale.NORMAL,
        help_text=_(
            "Ajusta el texto de lectura de toda la tienda. Elige Grande para facilitar su lectura."
        ),
    )
    business_locality = models.CharField(
        _("Ciudad"), max_length=100, default="Armenia", db_default="Armenia"
    )
    business_region = models.CharField(
        _("Departamento"), max_length=100, default="Quindío", db_default="Quindío"
    )
    business_country = models.CharField(
        _("Código del país"), max_length=2, default="CO", db_default="CO"
    )
    appointment_only = models.BooleanField(
        _("Atención solo con cita"), default=True, db_default=True
    )
    service_area = models.CharField(
        _("Área de servicio"), max_length=100, default="Colombia", db_default="Colombia"
    )
    opening_hours_es = models.CharField(
        _("Horario (español)"),
        max_length=250,
        default="Atención 24 horas por WhatsApp · Citas con agendamiento previo",
        db_default="Atención 24 horas por WhatsApp · Citas con agendamiento previo",
    )
    opening_hours_en = models.CharField(
        _("Horario (inglés)"),
        max_length=250,
        default="24-hour WhatsApp support · Visits by appointment",
        db_default="24-hour WhatsApp support · Visits by appointment",
    )
    seo_home_title_es = models.CharField(
        _("Título SEO del inicio (español)"),
        max_length=200,
        default="SERTI · Joyería en Armenia, Quindío | Esmeraldas colombianas y oro 18k",
        db_default="SERTI · Joyería en Armenia, Quindío | Esmeraldas colombianas y oro 18k",
    )
    seo_home_title_en = models.CharField(
        _("Título SEO del inicio (inglés)"),
        max_length=200,
        default="SERTI · Fine jewelry from Armenia, Colombia | Colombian emeralds & 18k gold",
        db_default="SERTI · Fine jewelry from Armenia, Colombia | Colombian emeralds & 18k gold",
    )
    seo_home_description_es = models.TextField(
        _("Descripción SEO del inicio (español)"),
        default="Joyería de autor en Armenia, Quindío: anillos, cadenas, aretes y dijes en oro 18k con esmeraldas colombianas. Atención con cita y envíos a toda Colombia.",  # noqa: E501
        db_default="Joyería de autor en Armenia, Quindío: anillos, cadenas, aretes y dijes en oro 18k con esmeraldas colombianas. Atención con cita y envíos a toda Colombia.",  # noqa: E501
    )
    seo_home_description_en = models.TextField(
        _("Descripción SEO del inicio (inglés)"),
        default="Fine jewelry from Armenia, Colombia: rings, chains, earrings and pendants in 18k gold with Colombian emeralds. By appointment, shipping across Colombia.",  # noqa: E501
        db_default="Fine jewelry from Armenia, Colombia: rings, chains, earrings and pendants in 18k gold with Colombian emeralds. By appointment, shipping across Colombia.",  # noqa: E501
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
