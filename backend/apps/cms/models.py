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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Illustrated(Timestamped):
    image = models.ImageField(upload_to="cms/", blank=True)
    image_alt = models.CharField(max_length=300, blank=True)
    renditions = models.JSONField(default=dict, blank=True, editable=False)
    width = models.PositiveIntegerField(default=0, editable=False)
    height = models.PositiveIntegerField(default=0, editable=False)

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

    kind = models.CharField(max_length=20, choices=Kind, unique=True)
    title = models.CharField(max_length=250)
    slug = models.SlugField(max_length=250, blank=True)
    body = models.TextField(blank=True)
    status = models.CharField(
        max_length=10,
        choices=[("draft", _("Borrador")), ("published", _("Publicada"))],
        default="draft",
        editable=False,
    )
    version = models.PositiveIntegerField(default=0, editable=False)
    published_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = _("página")
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
    position = models.PositiveIntegerField(default=0)
    is_visible = models.BooleanField(default=True)
    title = models.CharField(
        max_length=300,
        blank=True,
        help_text=_(
            "Usa « / » para separar líneas; con varias líneas, la última se muestra en cursiva. "
            "Ejemplo: Un poco de tierra. / Un poco de eternidad."
        ),
    )
    subtitle = models.TextField(blank=True)
    body = models.TextField(blank=True)
    cta_label = models.CharField(max_length=150, blank=True)
    cta_kind = models.CharField(
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
        "catalog.Category", on_delete=models.PROTECT, null=True, blank=True
    )
    cta_stone = models.ForeignKey("catalog.Stone", on_delete=models.PROTECT, null=True, blank=True)
    cta_collection = models.ForeignKey(
        "catalog.Collection",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cta_sections",
    )
    cta_piece = models.ForeignKey("catalog.Piece", on_delete=models.PROTECT, null=True, blank=True)
    cta_page = models.ForeignKey(Page, on_delete=models.PROTECT, null=True, blank=True)
    cta_external_url = models.URLField(blank=True, validators=[validate_https])
    collection = models.ForeignKey(
        "catalog.Collection",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="home_sections",
    )

    class Meta:
        ordering = ["position", "pk"]
        verbose_name = _("sección del inicio")
        permissions = [("publish_content", "Puede publicar y restaurar contenido")]

    def __str__(self) -> str:
        return self.title or self.kind


SnapshotT = TypeVar("SnapshotT", bound=models.Model)


class ImmutableQuerySet(models.QuerySet[SnapshotT]):
    def update(self, **kwargs: Any) -> int:
        raise ValidationError(_("Las publicaciones son inmutables."))

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError(_("Las publicaciones son inmutables."))


class ImmutableSnapshot(models.Model):
    snapshot = models.JSONField()
    # SET_NULL + name snapshot (like the audit log): a staff member who published content
    # must remain deletable when they leave, without losing who published what.
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    published_by_repr = models.CharField(max_length=150, blank=True)
    published_at = models.DateTimeField(auto_now_add=True)

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
    note = models.CharField(max_length=300, blank=True)
    # Keep editable source separate from the public snapshot, including hidden sections.
    draft_snapshot = models.JSONField(default=list, editable=False)
    objects = ImmutableQuerySet["HomePublication"].as_manager()

    class Meta(ImmutableSnapshot.Meta):
        verbose_name = _("publicación del inicio")

    def __str__(self) -> str:
        return str(self.published_at)


class PageRevision(ImmutableSnapshot):
    page = models.ForeignKey(Page, on_delete=models.PROTECT, related_name="revisions")
    version = models.PositiveIntegerField()
    objects = ImmutableQuerySet["PageRevision"].as_manager()

    class Meta(ImmutableSnapshot.Meta):
        verbose_name = _("revisión de página")
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
    title = models.CharField(max_length=250)
    description = models.TextField(blank=True)
    whatsapp_message = models.TextField(default="Hola SERTI, me interesa {service}. {url}")
    is_active = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "pk"]
        verbose_name = _("servicio de personalización")

    def __str__(self) -> str:
        return self.title
