from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from modeltranslation.manager import MultilingualManager

from apps.core.money import Money

from .validators import validate_attributes


def original_path(instance: PieceImage, filename: str) -> str:
    return f"pieces/originals/{uuid.uuid4().hex}.webp"


class NamedModel(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, blank=True)
    position = models.PositiveIntegerField(default=0)

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


class CoveredModel(NamedModel):
    description = models.TextField(blank=True)
    cover_image = models.ImageField(upload_to="catalog/covers/", blank=True)

    class Meta(NamedModel.Meta):
        abstract = True


class Category(CoveredModel):
    objects: MultilingualManager[Category] = MultilingualManager()
    seo_title = models.CharField(max_length=200, blank=True)
    seo_description = models.TextField(blank=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    is_active = models.BooleanField(default=True)

    class Meta(CoveredModel.Meta):
        abstract = False
        verbose_name = _("categoría")
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
    objects: MultilingualManager[Collection] = MultilingualManager()
    seo_title = models.CharField(max_length=200, blank=True)
    seo_description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    pieces: models.ManyToManyField[Piece, CollectionPiece] = models.ManyToManyField(
        "Piece", through="CollectionPiece", related_name="collections"
    )

    class Meta(CoveredModel.Meta):
        abstract = False
        verbose_name = _("colección")


class Stone(CoveredModel):
    objects: MultilingualManager[Stone] = MultilingualManager()

    class Meta(CoveredModel.Meta):
        abstract = False
        verbose_name = _("piedra")


class Material(NamedModel):
    objects: MultilingualManager[Material] = MultilingualManager()

    class Meta(NamedModel.Meta):
        abstract = False
        verbose_name = _("material")


class Piece(NamedModel):
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

    sku = models.CharField(max_length=40, unique=True)
    piece_number = models.CharField(max_length=20, blank=True)
    short_description = models.TextField(blank=True)
    long_description = models.TextField(blank=True)
    story = models.TextField(blank=True)
    care = models.TextField(blank=True)
    seo_title = models.CharField(max_length=200, blank=True)
    seo_description = models.TextField(blank=True)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="pieces", null=True, blank=True
    )
    stones = models.ManyToManyField(Stone, related_name="pieces", blank=True)
    materials = models.ManyToManyField(Material, related_name="pieces", blank=True)
    related = models.ManyToManyField(
        "self",
        symmetrical=False,
        blank=True,
        through="PieceRelation",
        through_fields=("source", "target"),
    )
    status = models.CharField(max_length=12, choices=Status, default=Status.DRAFT)
    sale_state = models.CharField(
        max_length=12, choices=SaleState, default=SaleState.AVAILABLE, editable=False
    )
    is_new = models.BooleanField(default=False)
    price_cents = models.BigIntegerField()
    sale_price_cents = models.BigIntegerField(null=True, blank=True)
    attributes = models.JSONField(default=dict, blank=True, validators=[validate_attributes])
    published_at = models.DateTimeField(null=True, blank=True, editable=False)
    sold_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta(NamedModel.Meta):
        abstract = False
        verbose_name = _("pieza")
        permissions = [("change_piece_price", "Puede cambiar precios de piezas")]
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
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE)
    piece = models.ForeignKey(Piece, on_delete=models.CASCADE)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["collection", "piece"], name="unique_collection_piece")
        ]

    def __str__(self) -> str:
        return f"{self.collection_id}: {self.piece_id}"


class PieceImage(models.Model):
    objects: MultilingualManager[PieceImage] = MultilingualManager()

    class ProcessingStatus(models.TextChoices):
        PENDING = "pending", _("Pendiente")
        READY = "ready", _("Lista")
        FAILED = "failed", _("Fallida")

    piece = models.ForeignKey(Piece, on_delete=models.CASCADE, related_name="images")
    original = models.ImageField(upload_to=original_path)
    renditions = models.JSONField(default=dict, blank=True)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    alt = models.CharField(max_length=300)
    position = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(default=False)
    processing_status = models.CharField(
        max_length=8, choices=ProcessingStatus, default=ProcessingStatus.PENDING
    )
    error = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["position", "pk"]
        verbose_name = _("imagen de pieza")
        constraints = [
            models.UniqueConstraint(
                fields=["piece"],
                condition=models.Q(is_primary=True),
                name="one_primary_image_per_piece",
            ),
            models.UniqueConstraint(
                fields=["piece", "position"], name="unique_image_position_per_piece"
            ),
        ]

    def __str__(self) -> str:
        return self.alt


class PieceRelation(models.Model):
    source = models.ForeignKey(Piece, on_delete=models.CASCADE, related_name="outgoing_relations")
    target = models.ForeignKey(Piece, on_delete=models.CASCADE, related_name="incoming_relations")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "target"], name="unique_related_piece"),
            models.CheckConstraint(
                condition=~models.Q(source=models.F("target")), name="piece_not_related_to_self"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source_id} → {self.target_id}"
