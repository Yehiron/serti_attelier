from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from modeltranslation.manager import MultilingualManager


def validate_https(value: str) -> None:
    URLValidator(schemes=["https"])(value)


class Timestamped(models.Model):
    created_at = models.DateTimeField(verbose_name=_("Creado el"), auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name=_("Actualizado el"), auto_now=True)

    class Meta:
        abstract = True


class Illustrated(Timestamped):
    image = models.ImageField(verbose_name=_("Imagen"), upload_to="cms/", blank=True)
    image_alt = models.CharField(verbose_name=_("Texto alternativo"), max_length=300, blank=True)
    renditions = models.JSONField(
        verbose_name=_("Versiones de imagen"), default=dict, blank=True, editable=False
    )
    width = models.PositiveIntegerField(verbose_name=_("Ancho"), default=0, editable=False)
    height = models.PositiveIntegerField(verbose_name=_("Alto"), default=0, editable=False)

    class Meta:
        abstract = True


class Page(Timestamped):
    if TYPE_CHECKING:
        title_es: str
        title_en: str
        slug_es: str
        slug_en: str
        body_es: str
        body_en: str

    objects: MultilingualManager[Page] = MultilingualManager()

    class Kind(models.TextChoices):
        TERMS = "terms", _("Términos")
        PRIVACY = "privacy", _("Privacidad")
        RETURNS = "returns", _("Devoluciones")
        SHIPPING = "shipping", _("Envíos")
        COOKIES = "cookies", _("Cookies")
        MANUFACTURER = "manufacturer", _("Fabricante")
        PERSONALIZE = "personalize", _("Personalización")
        CONTACT = "contact", _("Contacto")

    kind = models.CharField(verbose_name=_("Tipo"), max_length=20, choices=Kind, unique=True)
    title = models.CharField(verbose_name=_("Título"), max_length=250)
    slug = models.SlugField(verbose_name=_("Slug"), max_length=250, blank=True)
    body = models.TextField(verbose_name=_("Contenido"), blank=True)
    status = models.CharField(
        verbose_name=_("Estado"),
        max_length=10,
        choices=[("draft", _("Borrador")), ("published", _("Publicada"))],
        default="draft",
        editable=False,
    )
    version = models.PositiveIntegerField(verbose_name=_("Versión"), default=0, editable=False)
    published_at = models.DateTimeField(
        verbose_name=_("Publicada el"), null=True, blank=True, editable=False
    )

    class Meta:
        verbose_name = _("página")
        verbose_name_plural = _("páginas")
        constraints = [
            models.UniqueConstraint(fields=["slug_es"], name="cms_page_slug_es_unique"),
            models.UniqueConstraint(
                fields=["slug_en"], condition=~models.Q(slug_en=""), name="cms_page_slug_en_unique"
            ),
        ]

    def __str__(self) -> str:
        return self.title


class HomeSection(Illustrated):
    if TYPE_CHECKING:
        title_es: str
        title_en: str

    objects: MultilingualManager[HomeSection] = MultilingualManager()
    kind = models.CharField(
        verbose_name=_("Tipo"),
        max_length=24,
        choices=[
            ("hero", _("Portada")),
            ("statement", _("Manifiesto")),
            ("stone_panels", _("Piedras")),
            ("collection_rail", _("Colección")),
            ("story", _("Historia")),
            ("personalize", _("Personalización")),
            ("banner", _("Banner")),
        ],
    )
    position = models.PositiveIntegerField(verbose_name=_("Posición"), default=0)
    is_visible = models.BooleanField(verbose_name=_("Visible"), default=True)
    title = models.CharField(
        verbose_name=_("Título"),
        max_length=300,
        blank=True,
        help_text=_(
            "Usa « / » para separar líneas; con varias líneas, la última se muestra en cursiva. "
            "Ejemplo: Un poco de tierra. / Un poco de eternidad."
        ),
    )
    subtitle = models.TextField(verbose_name=_("Subtítulo"), blank=True)
    body = models.TextField(verbose_name=_("Contenido"), blank=True)
    cta_label = models.CharField(verbose_name=_("Texto del enlace"), max_length=150, blank=True)
    cta_kind = models.CharField(
        verbose_name=_("Tipo de enlace"),
        max_length=20,
        default="none",
        choices=[
            ("none", _("Sin enlace")),
            ("catalog", _("Catálogo")),
            ("category", _("Categoría")),
            ("stone", _("Piedra")),
            ("collection", _("Colección")),
            ("piece", _("Pieza")),
            ("personalize", _("Personalización")),
            ("story", _("Historia")),
            ("contact", _("Contacto")),
            ("page", _("Página legal")),
            ("external", _("Enlace externo")),
        ],
    )
    cta_category = models.ForeignKey(
        "catalog.Category",
        verbose_name=_("Categoría del enlace"),
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    cta_stone = models.ForeignKey(
        "catalog.Stone",
        verbose_name=_("Piedra del enlace"),
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    cta_collection = models.ForeignKey(
        "catalog.Collection",
        verbose_name=_("Colección del enlace"),
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cta_sections",
    )
    cta_piece = models.ForeignKey(
        "catalog.Piece",
        verbose_name=_("Pieza del enlace"),
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    cta_page = models.ForeignKey(
        Page, verbose_name=_("Página del enlace"), on_delete=models.PROTECT, null=True, blank=True
    )
    cta_external_url = models.URLField(
        verbose_name=_("Enlace externo"), blank=True, validators=[validate_https]
    )
    collection = models.ForeignKey(
        "catalog.Collection",
        verbose_name=_("Colección"),
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="home_sections",
    )

    class Meta:
        verbose_name = _("sección de la página de inicio")
        verbose_name_plural = _("Página de inicio")
        ordering = ["position", "pk"]
        permissions = [("publish_content", "Puede publicar y restaurar contenido")]

    def __str__(self) -> str:
        return self.title or self.kind


class HeroSlide(Timestamped):
    if TYPE_CHECKING:
        alt_es: str
        alt_en: str

    objects: MultilingualManager[HeroSlide] = MultilingualManager()
    section = models.ForeignKey(
        HomeSection,
        on_delete=models.CASCADE,
        related_name="slides",
        limit_choices_to={"kind": "hero"},
        verbose_name=_("Portada"),
    )

    class Device(models.TextChoices):
        DESKTOP = "desktop", _("Computador")
        MOBILE = "mobile", _("Celular")

    device = models.CharField(
        verbose_name=_("Dispositivo"), max_length=7, choices=Device, default=Device.DESKTOP
    )
    position = models.PositiveIntegerField(verbose_name=_("Posición"), default=0)
    image = models.ImageField(
        verbose_name=_("Foto"),
        upload_to="cms/slides/",
        blank=True,
        help_text=_("Conserva la proporción de la foto original."),
    )
    renditions = models.JSONField(
        verbose_name=_("Versiones de imagen"), default=dict, blank=True, editable=False
    )
    width = models.PositiveIntegerField(verbose_name=_("Ancho"), default=0, editable=False)
    height = models.PositiveIntegerField(verbose_name=_("Alto"), default=0, editable=False)
    alt = models.CharField(verbose_name=_("Texto alternativo"), max_length=300, blank=True)

    class Meta:
        verbose_name = _("diapositiva")
        verbose_name_plural = _("Diapositivas")
        ordering = ["position", "pk"]

    def __str__(self) -> str:
        return self.alt or str(self.position)

    def clean(self) -> None:
        super().clean()
        if self.section_id and self.section.kind != "hero":
            raise ValidationError(_("Las diapositivas solo pertenecen a una portada."))
        if not self.image:
            raise ValidationError(_("Agrega una imagen."))
        if any(not getattr(self, f"alt_{locale}", "") for locale in ("es", "en")):
            raise ValidationError(_("Escribe el texto alternativo en español e inglés."))


SnapshotT = TypeVar("SnapshotT", bound=models.Model)


class ImmutableQuerySet(models.QuerySet[SnapshotT]):
    def update(self, **kwargs: Any) -> int:
        raise ValidationError(_("Las publicaciones son inmutables."))

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError(_("Las publicaciones son inmutables."))


class ImmutableSnapshot(models.Model):
    snapshot = models.JSONField(verbose_name=_("Copia de publicación"))
    # SET_NULL + name snapshot (like the audit log): a staff member who published content
    # must remain deletable when they leave, without losing who published what.
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Publicado por"),
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    published_by_repr = models.CharField(
        verbose_name=_("Nombre de quien publicó"), max_length=150, blank=True
    )
    published_at = models.DateTimeField(verbose_name=_("Publicada el"), auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ["-published_at", "-pk"]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding or (
            self.pk is not None and type(self)._default_manager.filter(pk=self.pk).exists()
        ):
            raise ValidationError(_("Las publicaciones son inmutables."))
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValidationError(_("Las publicaciones son inmutables."))


class HomePublication(ImmutableSnapshot):
    note = models.CharField(verbose_name=_("Nota"), max_length=300, blank=True)
    # Keep editable source separate from the public snapshot, including hidden sections.
    draft_snapshot = models.JSONField(
        verbose_name=_("Copia del borrador"), default=list, editable=False
    )
    objects = ImmutableQuerySet["HomePublication"].as_manager()

    class Meta(ImmutableSnapshot.Meta):
        verbose_name = _("publicación del inicio")
        verbose_name_plural = _("publicaciones del inicio")

    def __str__(self) -> str:
        return str(self.published_at)


class PageRevision(ImmutableSnapshot):
    page = models.ForeignKey(
        Page, verbose_name=_("Página"), on_delete=models.PROTECT, related_name="revisions"
    )
    version = models.PositiveIntegerField(verbose_name=_("Versión"))
    objects = ImmutableQuerySet["PageRevision"].as_manager()

    class Meta(ImmutableSnapshot.Meta):
        verbose_name = _("revisión de página")
        verbose_name_plural = _("revisiones de páginas")
        constraints = [
            models.UniqueConstraint(fields=["page", "version"], name="cms_page_version_unique")
        ]

    def __str__(self) -> str:
        return f"{self.page_id} · {self.version}"


class PersonalizationService(Illustrated):
    if TYPE_CHECKING:
        whatsapp_message_es: str
        whatsapp_message_en: str

    objects: MultilingualManager[PersonalizationService] = MultilingualManager()
    title = models.CharField(verbose_name=_("Título"), max_length=250)
    description = models.TextField(verbose_name=_("Descripción"), blank=True)
    whatsapp_message = models.TextField(
        verbose_name=_("Mensaje de WhatsApp"), default="Hola SERTI, me interesa {service}. {url}"
    )
    is_active = models.BooleanField(verbose_name=_("Activo"), default=False)
    position = models.PositiveIntegerField(verbose_name=_("Posición"), default=0)

    class Meta:
        verbose_name = _("servicio de personalización")
        verbose_name_plural = _("servicios de personalización")
        ordering = ["position", "pk"]

    def __str__(self) -> str:
        return self.title
