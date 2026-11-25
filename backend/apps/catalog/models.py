from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from modeltranslation.manager import MultilingualManager

from apps.core.money import Money
from apps.payments.storage import private_storage

from .validators import validate_attributes


def original_path(instance: PieceImage, filename: str) -> str:
    return f"pieces/originals/{uuid.uuid4().hex}.webp"


class NamedModel(models.Model):
    if TYPE_CHECKING:
        name_es: str
        name_en: str
        slug_es: str
        slug_en: str

    name = models.CharField(verbose_name=_("Nombre"), max_length=200)
    slug = models.SlugField(verbose_name=_("Slug"), max_length=220, blank=True)
    position = models.PositiveIntegerField(verbose_name=_("Posición"), default=0)

    class Meta:
        abstract = True
        ordering = ["position", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["slug_es"], name="%(app_label)s_%(class)s_slug_es_unique"
            ),
            models.UniqueConstraint(
                fields=["slug_en"],
                condition=~models.Q(slug_en=""),
                name="%(app_label)s_%(class)s_slug_en_unique",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args: Any, **kwargs: Any) -> None:
        generated = self.populate_slugs()
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | generated
            if hasattr(self, "updated_at"):
                kwargs["update_fields"].add("updated_at")
        super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        self.populate_slugs()

    def populate_slugs(self) -> set[str]:
        generated = set()
        for language in ("es", "en"):
            field = f"slug_{language}"
            if getattr(self, field):
                continue
            name = getattr(self, f"name_{language}") or self.name_es
            base = (slugify(name or "") or "pieza")[:210]
            candidate, suffix = base, 2
            while (
                type(self)
                ._default_manager.filter(**{field: candidate})
                .exclude(pk=self.pk)
                .exists()
            ):
                candidate = f"{base}-{suffix}"
                suffix += 1
            setattr(self, field, candidate)
            generated.add(field)
        return generated


class CoveredModel(NamedModel):
    cover_renditions = models.JSONField(
        verbose_name=_("Versiones de portada"), default=dict, blank=True, editable=False
    )
    cover_width = models.PositiveIntegerField(
        verbose_name=_("Ancho de portada"), default=0, editable=False
    )
    cover_height = models.PositiveIntegerField(
        verbose_name=_("Alto de portada"), default=0, editable=False
    )
    description = models.TextField(verbose_name=_("Descripción"), blank=True)
    cover_image = models.ImageField(
        verbose_name=_("Imagen de portada"), upload_to="catalog/covers/", blank=True
    )

    class Meta(NamedModel.Meta):
        abstract = True


class Category(CoveredModel):
    updated_at = models.DateTimeField(verbose_name=_("Actualizado el"), auto_now=True, null=True)
    objects: MultilingualManager[Category] = MultilingualManager()
    seo_title = models.CharField(verbose_name=_("Título SEO"), max_length=200, blank=True)
    seo_description = models.TextField(verbose_name=_("Descripción SEO"), blank=True)
    parent = models.ForeignKey(
        "self",
        verbose_name=_("Categoría superior"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    is_active = models.BooleanField(verbose_name=_("Activo"), default=True)

    class Meta(CoveredModel.Meta):
        verbose_name = _("categoría")
        verbose_name_plural = _("categorías")
        abstract = False
        constraints = [
            *CoveredModel.Meta.constraints,
            models.CheckConstraint(
                condition=~models.Q(parent=models.F("pk")), name="category_not_own_parent"
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.parent_id and (
            self.parent_id == self.pk
            or (self.parent is not None and self.parent.parent_id)
            or (self.pk and self.children.exists())
        ):
            raise ValidationError({"parent": _("Solo se permite un nivel de subcategorías.")})


class Collection(CoveredModel):
    updated_at = models.DateTimeField(verbose_name=_("Actualizado el"), auto_now=True, null=True)
    objects: MultilingualManager[Collection] = MultilingualManager()
    seo_title = models.CharField(verbose_name=_("Título SEO"), max_length=200, blank=True)
    seo_description = models.TextField(verbose_name=_("Descripción SEO"), blank=True)
    is_active = models.BooleanField(verbose_name=_("Activo"), default=True)
    pieces: models.ManyToManyField[Piece, CollectionPiece] = models.ManyToManyField(
        "Piece", verbose_name=_("Piezas"), through="CollectionPiece", related_name="collections"
    )

    class Meta(CoveredModel.Meta):
        verbose_name = _("colección")
        verbose_name_plural = _("colecciones")
        abstract = False


class Stone(CoveredModel):
    updated_at = models.DateTimeField(verbose_name=_("Actualizado el"), auto_now=True, null=True)
    objects: MultilingualManager[Stone] = MultilingualManager()

    class Meta(CoveredModel.Meta):
        verbose_name = _("piedra")
        verbose_name_plural = _("piedras")
        abstract = False


class Material(NamedModel):
    updated_at = models.DateTimeField(verbose_name=_("Actualizado el"), auto_now=True, null=True)
    objects: MultilingualManager[Material] = MultilingualManager()

    class Meta(NamedModel.Meta):
        verbose_name = _("material")
        verbose_name_plural = _("materiales")
        abstract = False


class Piece(NamedModel):
    if TYPE_CHECKING:
        short_description_es: str
        short_description_en: str | None

    updated_at = models.DateTimeField(verbose_name=_("Actualizado el"), auto_now=True, null=True)
    objects: MultilingualManager[Piece] = MultilingualManager()

    class Status(models.TextChoices):
        DRAFT = "draft", _("Borrador")
        PUBLISHED = "published", _("Publicada")
        HIDDEN = "hidden", _("Oculta")
        ARCHIVED = "archived", _("Archivada")

    class SaleState(models.TextChoices):
        AVAILABLE = "available", _("Disponible")
        RESERVED = "reserved", _("Reservada")
        SOLD = "sold", _("Vendida")
        PREORDER = "preorder", _("Preventa")

    sku = models.CharField(verbose_name=_("SKU"), max_length=40, unique=True)
    piece_number = models.CharField(verbose_name=_("Número de pieza"), max_length=20, blank=True)
    short_description = models.TextField(verbose_name=_("Descripción corta"), blank=True)
    long_description = models.TextField(verbose_name=_("Descripción larga"), blank=True)
    story = models.TextField(verbose_name=_("Historia"), blank=True)
    care = models.TextField(verbose_name=_("Cuidados"), blank=True)
    seo_title = models.CharField(verbose_name=_("Título SEO"), max_length=200, blank=True)
    seo_description = models.TextField(verbose_name=_("Descripción SEO"), blank=True)
    category = models.ForeignKey(
        Category,
        verbose_name=_("Categoría"),
        on_delete=models.PROTECT,
        related_name="pieces",
        null=True,
        blank=True,
    )
    stones = models.ManyToManyField(
        Stone, verbose_name=_("Piedras"), related_name="pieces", blank=True
    )
    materials = models.ManyToManyField(
        Material, verbose_name=_("Materiales"), related_name="pieces", blank=True
    )
    related = models.ManyToManyField(
        "self",
        verbose_name=_("Piezas relacionadas"),
        symmetrical=False,
        blank=True,
        through="PieceRelation",
        through_fields=("source", "target"),
    )
    status = models.CharField(
        verbose_name=_("Estado"), max_length=12, choices=Status, default=Status.DRAFT
    )
    sale_state = models.CharField(
        verbose_name=_("Estado de venta"),
        max_length=12,
        choices=SaleState,
        default=SaleState.AVAILABLE,
        editable=False,
    )
    is_new = models.BooleanField(verbose_name=_("Novedad"), default=False)
    price_cents = models.BigIntegerField(verbose_name=_("Precio (centavos)"))
    sale_price_cents = models.BigIntegerField(
        verbose_name=_("Precio de oferta (centavos)"), null=True, blank=True
    )
    attributes = models.JSONField(
        verbose_name=_("Atributos"), default=dict, blank=True, validators=[validate_attributes]
    )
    published_at = models.DateTimeField(
        verbose_name=_("Publicada el"), null=True, blank=True, editable=False
    )
    sold_at = models.DateTimeField(
        verbose_name=_("Vendida el"), null=True, blank=True, editable=False
    )

    class Meta(NamedModel.Meta):
        verbose_name = _("pieza")
        verbose_name_plural = _("piezas")
        abstract = False
        permissions = [
            ("change_piece_price", "Puede cambiar precios de piezas"),
            ("publish_piece", "Puede publicar y retirar piezas"),
        ]
        constraints = [
            *NamedModel.Meta.constraints,
            models.CheckConstraint(
                condition=models.Q(price_cents__gt=0), name="piece_positive_price"
            ),
            models.CheckConstraint(
                condition=models.Q(sale_price_cents__isnull=True)
                | models.Q(sale_price_cents__gt=0, sale_price_cents__lt=models.F("price_cents")),
                name="piece_valid_sale_price",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "sale_state"]),
            models.Index(fields=["category", "status"]),
            models.Index(fields=["-published_at"]),
            models.Index(
                fields=["status", "sale_state", "-published_at", "-id"],
                name="piece_public_order_idx",
            ),
        ]

    @property
    def effective_price(self) -> Money:
        return Money(
            self.sale_price_cents if self.sale_price_cents is not None else self.price_cents
        )

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        if self.status != self.Status.DRAFT:
            raise ValidationError(_("Solo se pueden eliminar borradores."))
        return super().delete(*args, **kwargs)


class CollectionPiece(models.Model):
    collection = models.ForeignKey(
        Collection, verbose_name=_("Colección"), on_delete=models.CASCADE
    )
    piece = models.ForeignKey(Piece, verbose_name=_("Pieza"), on_delete=models.CASCADE)
    position = models.PositiveIntegerField(verbose_name=_("Posición"), default=0)

    class Meta:
        verbose_name = _("pieza de colección")
        verbose_name_plural = _("piezas de colecciones")
        ordering = ["position", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["collection", "piece"], name="unique_collection_piece")
        ]

    def __str__(self) -> str:
        return f"{self.collection_id}: {self.piece_id}"


class PieceImage(models.Model):
    if TYPE_CHECKING:
        alt_es: str
        alt_en: str | None

    objects: MultilingualManager[PieceImage] = MultilingualManager()

    class ProcessingStatus(models.TextChoices):
        PENDING = "pending", _("Pendiente")
        READY = "ready", _("Lista")
        FAILED = "failed", _("Fallida")

    piece = models.ForeignKey(
        Piece, verbose_name=_("Pieza"), on_delete=models.CASCADE, related_name="images"
    )
    original = models.ImageField(verbose_name=_("Archivo original"), upload_to=original_path)
    renditions = models.JSONField(verbose_name=_("Versiones de imagen"), default=dict, blank=True)
    width = models.PositiveIntegerField(verbose_name=_("Ancho"), default=0)
    height = models.PositiveIntegerField(verbose_name=_("Alto"), default=0)
    alt = models.CharField(verbose_name=_("Texto alternativo"), max_length=300)
    position = models.PositiveIntegerField(verbose_name=_("Posición"), default=0)
    is_primary = models.BooleanField(
        default=False,
        verbose_name=_("Imagen principal"),
        help_text=_("Se muestra como imagen principal de la pieza y de sus tarjetas."),
    )
    is_hover = models.BooleanField(
        default=False,
        verbose_name=_("Imagen al pasar el cursor"),
        help_text=_(
            "Opcional. Se muestra al pasar el cursor sobre la tarjeta en computador. "
            "Usa una foto alternativa de la misma pieza."
        ),
    )
    processing_status = models.CharField(
        verbose_name=_("Estado de procesamiento"),
        max_length=8,
        choices=ProcessingStatus,
        default=ProcessingStatus.PENDING,
    )
    error = models.CharField(verbose_name=_("Error"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("imagen de pieza")
        verbose_name_plural = _("imágenes de piezas")
        ordering = ["position", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["piece"],
                condition=models.Q(is_primary=True),
                name="one_primary_image_per_piece",
            ),
            models.UniqueConstraint(
                fields=["piece"],
                condition=models.Q(is_hover=True),
                name="one_hover_image_per_piece",
            ),
            models.CheckConstraint(
                condition=~models.Q(is_primary=True, is_hover=True),
                name="image_not_primary_and_hover",
            ),
            models.UniqueConstraint(
                fields=["piece", "position"], name="unique_image_position_per_piece"
            ),
        ]

    def __str__(self) -> str:
        return self.alt


class PieceRelation(models.Model):
    source = models.ForeignKey(
        Piece, verbose_name=_("Origen"), on_delete=models.CASCADE, related_name="outgoing_relations"
    )
    target = models.ForeignKey(
        Piece,
        verbose_name=_("Destino"),
        on_delete=models.CASCADE,
        related_name="incoming_relations",
    )

    class Meta:
        verbose_name = _("relación de piezas")
        verbose_name_plural = _("relaciones de piezas")
        constraints = [
            models.UniqueConstraint(fields=["source", "target"], name="unique_related_piece"),
            models.CheckConstraint(
                condition=~models.Q(source=models.F("target")), name="piece_not_related_to_self"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source_id} → {self.target_id}"


def video_original_path(instance: PieceVideo, filename: str) -> str:
    return f"pieces/videos/originals/{uuid.uuid4().hex}"


class PieceVideo(models.Model):
    objects: MultilingualManager[PieceVideo] = MultilingualManager()
    piece = models.OneToOneField(
        Piece, verbose_name=_("Pieza"), on_delete=models.CASCADE, related_name="video"
    )
    original = models.FileField(
        verbose_name=_("Video original"),
        storage=private_storage,
        upload_to=video_original_path,
        blank=True,
        help_text=_(
            "Video corto (máx. 60 s, 150 MB). "
            "Se convierte automáticamente a MP4 liviano sin sonido."
        ),
    )
    mp4 = models.FileField(verbose_name=_("Video MP4"), upload_to="pieces/videos/", blank=True)
    poster = models.ImageField(
        verbose_name=_("Póster"), upload_to="pieces/videos/posters/", blank=True
    )
    poster_renditions = models.JSONField(
        verbose_name=_("Versiones del póster"), default=dict, blank=True
    )
    width = models.PositiveIntegerField(verbose_name=_("Ancho"), default=0)
    height = models.PositiveIntegerField(verbose_name=_("Alto"), default=0)
    duration_seconds = models.FloatField(verbose_name=_("Duración en segundos"), default=0)
    alt = models.CharField(verbose_name=_("Texto alternativo"), max_length=300)
    processing_status = models.CharField(
        verbose_name=_("Estado de procesamiento"),
        max_length=8,
        choices=PieceImage.ProcessingStatus,
        default=PieceImage.ProcessingStatus.PENDING,
    )
    error = models.CharField(verbose_name=_("Error"), max_length=200, blank=True)
    created_at = models.DateTimeField(verbose_name=_("Creado el"), auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name=_("Actualizado el"), auto_now=True)

    class Meta:
        verbose_name = _("video de pieza")
        verbose_name_plural = _("videos de piezas")

    def __str__(self) -> str:
        return self.alt
