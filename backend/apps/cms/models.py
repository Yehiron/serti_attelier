from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator, URLValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from modeltranslation.manager import MultilingualManager

from .registry import REGISTRY


def validate_https(value: str) -> None:
    URLValidator(schemes=["https"])(value)


class Timestamped(models.Model):
    created_at = models.DateTimeField(verbose_name=_("Creado el"), auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name=_("Actualizado el"), auto_now=True)

    class Meta:
        abstract = True


class Illustrated(Timestamped):
    image_reference = models.JSONField(
        _("Foto de biblioteca"), default=dict, blank=True, editable=False
    )
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
    slug = models.SlugField(verbose_name=_("Dirección de la página"), max_length=250, blank=True)
    body = models.TextField(verbose_name=_("Contenido"), blank=True)
    body_enabled = models.BooleanField(
        _("Contenido de Personaliza habilitado"), default=False, editable=False
    )
    slug_paths = models.JSONField(_("Direcciones elegidas"), default=dict, blank=True)
    process_title = models.CharField(
        _("Título de los pasos"), max_length=120, default="De una idea a tu joya"
    )
    faq_title = models.CharField(
        _("Título de las preguntas frecuentes"), max_length=120, default="Preguntas frecuentes"
    )
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


class ProcessStep(Timestamped):
    page = models.ForeignKey(
        Page,
        on_delete=models.CASCADE,
        related_name="process_steps",
        limit_choices_to={"kind": "personalize"},
        verbose_name=_("Página"),
    )
    position = models.PositiveIntegerField(_("Posición"), default=0)
    title = models.CharField(_("Paso"), max_length=60, help_text="Hasta 60 caracteres.")
    description = models.CharField(
        _("Descripción"), max_length=240, blank=True, help_text="Opcional. Hasta 240 caracteres."
    )

    class Meta:
        ordering = ["position", "pk"]
        verbose_name = "paso"
        verbose_name_plural = "Pasos"

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if self.page_id and self.page.kind != "personalize":
            raise ValidationError({"page": "Los pasos solo pertenecen a Personaliza."})


class FaqItem(Timestamped):
    page = models.ForeignKey(
        Page, on_delete=models.CASCADE, related_name="faq_items", verbose_name=_("Página")
    )
    position = models.PositiveIntegerField(_("Posición"), default=0)
    question = models.CharField(_("Pregunta"), max_length=160, help_text="Hasta 160 caracteres.")
    answer = models.TextField(
        _("Respuesta"),
        max_length=1500,
        validators=[MaxLengthValidator(1500)],
        help_text="Hasta 1500 caracteres. Puedes usar Markdown y enlaces internos, "
        "por ejemplo [Devoluciones](/es/legal/devoluciones).",
    )

    class Meta:
        ordering = ["position", "pk"]
        verbose_name = "pregunta frecuente"
        verbose_name_plural = "Preguntas frecuentes"

    def __str__(self):
        return self.question


class HomeSection(Illustrated):
    if TYPE_CHECKING:
        title_es: str
        title_en: str

    objects: MultilingualManager[HomeSection] = MultilingualManager()
    kind = models.CharField(
        verbose_name=_("Tipo"),
        max_length=24,
        choices=[(spec.kind, spec.name) for spec in REGISTRY.values()],
    )
    schema_version = models.PositiveSmallIntegerField(_("Versión del esquema"), default=1)
    props = models.JSONField(_("Contenido de la sección"), default=dict, blank=True)

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
        permissions = [
            ("publish_content", "Puede publicar contenido"),
            ("edit_content", "Puede editar contenido"),
            ("preview_content", "Puede previsualizar contenido"),
            ("restore_content", "Puede restaurar contenido"),
        ]

    def __str__(self) -> str:
        spec = REGISTRY.get(self.kind)
        if spec and spec.storage != "columns":
            from django.utils.translation import get_language

            title = self.props.get("title", {})
            return title.get(get_language()) or title.get("es") or spec.name
        return self.title or (spec.name if spec else self.kind)


class HeroSlide(Timestamped):
    image_reference = models.JSONField(
        _("Foto de biblioteca"), default=dict, blank=True, editable=False
    )
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
        if not self.image and not self.image_reference:
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
    seo = models.JSONField(_("Opciones para buscadores"), default=dict, blank=True)
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
    note = models.CharField(_("Nota"), max_length=300, blank=True)
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


class MenuPublication(ImmutableSnapshot):
    menu = models.CharField(
        _("Menú"), max_length=20, choices=[("main", "Principal"), ("footer", "Pie de página")]
    )
    note = models.CharField(_("Nota"), max_length=300, blank=True)
    objects = ImmutableQuerySet["MenuPublication"].as_manager()

    class Meta(ImmutableSnapshot.Meta):
        verbose_name = _("publicación de menú")
        verbose_name_plural = _("publicaciones de menús")

    def __str__(self):
        return f"{self.get_menu_display()} · {self.published_at}"


class BrandPublication(ImmutableSnapshot):
    note = models.CharField(_("Nota"), max_length=300, blank=True)
    objects = ImmutableQuerySet["BrandPublication"].as_manager()

    class Meta(ImmutableSnapshot.Meta):
        verbose_name = _("publicación de identidad de marca")
        verbose_name_plural = _("publicaciones de identidad de marca")

    def __str__(self):
        return f"Identidad de marca · {self.published_at}"


class Redirect(Timestamped):
    from_path = models.CharField(_("Dirección anterior"), max_length=500, unique=True)
    to_path = models.CharField(_("Dirección de destino"), max_length=500)
    locale = models.CharField(
        _("Idioma"), max_length=2, choices=[("es", "Español"), ("en", "Inglés")]
    )
    status_code = models.PositiveSmallIntegerField(
        _("Código de redirección"),
        default=301,
        choices=[(301, "301 · Permanente"), (308, "308 · Permanente")],
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Creada por"),
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    hits = models.PositiveBigIntegerField(_("Visitas redirigidas"), default=0)
    last_hit_at = models.DateTimeField(_("Última visita redirigida"), null=True, blank=True)
    is_active = models.BooleanField(_("Activa"), default=True)
    origin = models.CharField(
        _("Origen"),
        max_length=10,
        default="manual",
        choices=[("automatic", "Automática"), ("manual", "Manual")],
    )

    class Meta:
        verbose_name = _("redirección")
        verbose_name_plural = _("redirecciones")
        ordering = ["from_path"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(from_path=models.F("to_path")), name="cms_redirect_not_self"
            ),
            models.CheckConstraint(
                condition=models.Q(status_code__in=[301, 308]), name="cms_redirect_permanent"
            ),
        ]

    def __str__(self):
        return f"{self.from_path} → {self.to_path}"


class ContentDocument(models.Model):
    brand_identity = models.JSONField(_("Identidad de marca"), default=dict, blank=True)
    brand_publication = models.ForeignKey(
        BrandPublication,
        verbose_name=_("Publicación de identidad"),
        null=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    translation_exemptions = models.JSONField(
        _("Textos iguales en ambos idiomas"), default=dict, blank=True
    )
    seo = models.JSONField(_("Opciones para buscadores"), default=dict, blank=True)
    menu_items = models.JSONField(_("Enlaces del menú"), default=list, blank=True)
    menu_publication = models.ForeignKey(
        MenuPublication,
        verbose_name=_("Publicación del menú"),
        null=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    key = models.CharField(_("Identificador del documento"), max_length=50, unique=True)
    draft_version = models.PositiveBigIntegerField(_("Versión del borrador"), default=0)
    updated_at = models.DateTimeField(_("Actualizado el"), auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Actualizado por"),
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    published_version = models.BigIntegerField(_("Versión publicada del borrador"), null=True)
    home_publication = models.ForeignKey(
        HomePublication,
        verbose_name=_("Publicación del inicio"),
        null=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    page_revision = models.ForeignKey(
        PageRevision,
        verbose_name=_("Publicación de la página"),
        null=True,
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        verbose_name = _("documento de contenido")
        verbose_name_plural = _("documentos de contenido")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(draft_version__gte=0), name="cms_document_version_nonnegative"
            )
        ]

    def __str__(self):
        return self.key


class DraftRevision(ImmutableSnapshot):
    restored_from_brand = models.ForeignKey(
        BrandPublication,
        verbose_name=_("Publicación de identidad"),
        null=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    seo = models.JSONField(_("Opciones para buscadores"), default=dict, blank=True)
    restored_from_menu = models.ForeignKey(
        MenuPublication,
        verbose_name=_("Publicación del menú"),
        null=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    document = models.ForeignKey(
        ContentDocument,
        verbose_name=_("Documento"),
        on_delete=models.PROTECT,
        related_name="draft_revisions",
    )
    draft_version = models.PositiveBigIntegerField(_("Versión del borrador"))
    kind = models.CharField(
        _("Tipo de revisión"),
        max_length=10,
        default="restore",
        choices=[("restore", "Restauración")],
    )
    restored_from_home = models.ForeignKey(
        HomePublication,
        verbose_name=_("Publicación del inicio"),
        null=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    restored_from_page = models.ForeignKey(
        PageRevision,
        verbose_name=_("Publicación de la página"),
        null=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    objects = ImmutableQuerySet["DraftRevision"].as_manager()

    class Meta(ImmutableSnapshot.Meta):
        verbose_name = _("revisión de borrador")
        verbose_name_plural = _("revisiones de borrador")
        constraints = [
            models.UniqueConstraint(
                fields=["document", "draft_version"], name="cms_draft_revision_version_unique"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        restored_from_home__isnull=False,
                        restored_from_page__isnull=True,
                        restored_from_menu__isnull=True,
                        restored_from_brand__isnull=True,
                    )
                    | models.Q(
                        restored_from_home__isnull=True,
                        restored_from_page__isnull=False,
                        restored_from_menu__isnull=True,
                        restored_from_brand__isnull=True,
                    )
                    | models.Q(
                        restored_from_home__isnull=True,
                        restored_from_page__isnull=True,
                        restored_from_menu__isnull=False,
                        restored_from_brand__isnull=True,
                    )
                    | models.Q(
                        restored_from_home__isnull=True,
                        restored_from_page__isnull=True,
                        restored_from_menu__isnull=True,
                        restored_from_brand__isnull=False,
                    )
                ),
                name="cms_restore_one_origin",
            ),
        ]

    def __str__(self):
        return f"{self.document_id} · {self.draft_version}"

    @property
    def restored_from(self):
        return (
            self.restored_from_home
            or self.restored_from_page
            or self.restored_from_menu
            or self.restored_from_brand
        )


class MediaAsset(Timestamped):
    """CMS pixels only; catalog PieceImage has an independent lifecycle."""

    original = models.FileField(
        _("Original sin metadatos"), upload_to="cms/library/originals/", max_length=300
    )
    width = models.PositiveIntegerField(_("Ancho"), default=0)
    height = models.PositiveIntegerField(_("Alto"), default=0)
    media_type = models.CharField(_("Tipo de archivo"), max_length=30, default="image/webp")
    size = models.PositiveBigIntegerField(_("Peso en bytes"), default=0)
    sha256 = models.CharField(
        _("Huella SHA-256"), max_length=64, unique=True, null=True, blank=True
    )
    alt_es = models.CharField(_("Texto alternativo en español"), max_length=300, blank=True)
    alt_en = models.CharField(_("Texto alternativo en inglés"), max_length=300, blank=True)
    title = models.CharField(_("Título interno"), max_length=200, blank=True)
    tags = models.CharField(_("Etiquetas"), max_length=300, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("Subida por"), null=True, on_delete=models.SET_NULL
    )
    focal_x = models.FloatField(_("Punto horizontal"), default=0.5)
    focal_y = models.FloatField(_("Punto vertical"), default=0.5)
    crops = models.JSONField(_("Recortes"), default=dict, blank=True)
    version = models.PositiveIntegerField(_("Versión de la foto"), default=1)
    state = models.CharField(
        _("Estado"),
        max_length=12,
        default="processing",
        choices=[
            ("processing", "Preparando"),
            ("ready", "Lista"),
            ("failed", "No se pudo preparar"),
        ],
    )
    archived = models.BooleanField(_("Archivada"), default=False)
    # Append-only generations: existing references and published URLs never change.
    versions = models.JSONField(
        _("Versiones conservadas"), default=dict, blank=True, editable=False
    )
    legacy_key = models.CharField(_("Archivo anterior"), max_length=300, blank=True, db_index=True)

    legacy_fingerprint = models.CharField(
        _("Identificador de importación"), max_length=64, unique=True, null=True, blank=True
    )

    class Meta:
        verbose_name = _("foto de biblioteca")
        verbose_name_plural = _("Fotos de biblioteca")
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(focal_x__gte=0, focal_x__lte=1), name="cms_media_focal_x_range"
            ),
            models.CheckConstraint(
                condition=models.Q(focal_y__gte=0, focal_y__lte=1), name="cms_media_focal_y_range"
            ),
        ]

    def __str__(self):
        return self.title or self.alt_es or f"Foto {self.pk}"


class CacheInvalidation(models.Model):
    """Durable outbox; no secrets, URLs or transport exception payloads are stored."""

    tags = models.JSONField(_("etiquetas"))
    document_key = models.CharField(_("documento"), max_length=100, blank=True)
    state = models.CharField(
        _("estado"),
        max_length=12,
        default="pending",
        db_index=True,
        choices=[("pending", _("Pendiente")), ("sent", _("Actualizada")), ("failed", _("Fallida"))],
    )
    attempts = models.PositiveSmallIntegerField(_("intentos"), default=0)
    created_at = models.DateTimeField(_("creada el"), auto_now_add=True)
    updated_at = models.DateTimeField(_("actualizada el"), auto_now=True)

    class Meta:
        verbose_name = _("actualización de la tienda")
        verbose_name_plural = _("actualizaciones de la tienda")
        indexes = [models.Index(fields=["document_key", "-id"], name="cms_invalidation_latest")]

    def __str__(self):
        return f"Actualización {self.pk}: {self.get_state_display()}"
