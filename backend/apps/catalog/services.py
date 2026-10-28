from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.http import HttpRequest
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.audit.diff import compute_diff
from apps.audit.services import record
from apps.core.exceptions import PublicationError

from .images import crop_to_ratio, encode_webp, validated_image
from .models import Category, Collection, CollectionPiece, Material, Piece, PieceImage, Stone

Actor = User | AnonymousUser | None
Taxonomy = Category | Collection | Stone | Material


def snapshot(piece: Piece) -> dict[str, object]:
    return {
        field.name: (
            getattr(piece, field.attname).isoformat()
            if isinstance(getattr(piece, field.attname), datetime)
            else getattr(piece, field.attname)
        )
        for field in piece._meta.concrete_fields
        if not isinstance(field, models.FileField)
    }


@transaction.atomic
def save_piece(piece: Piece, *, actor: Actor, request: HttpRequest | None = None) -> Piece:
    old = Piece.objects.select_for_update().filter(pk=piece.pk).first() if piece.pk else None
    price_changed = (
        old is None and (piece.price_cents is not None or piece.sale_price_cents is not None)
    ) or (
        old is not None
        and (old.price_cents != piece.price_cents or old.sale_price_cents != piece.sale_price_cents)
    )
    if price_changed and actor is not None and not actor.has_perm("catalog.change_piece_price"):
        raise PermissionDenied(_("No tienes permiso para cambiar precios."))
    if old and (piece.sale_state != old.sale_state or piece.sold_at != old.sold_at):
        raise ValidationError(_("El estado de venta solo se cambia desde inventario."))
    if old and piece.status != old.status:
        raise ValidationError(_("Usa las acciones de publicación para cambiar el estado."))
    if old is None and (
        piece.status != Piece.Status.DRAFT or piece.sale_state != Piece.SaleState.AVAILABLE
    ):
        raise ValidationError(_("Las piezas nuevas deben ser borradores disponibles."))
    piece.full_clean()
    piece.save()
    diff = compute_diff(snapshot(old) if old else {}, snapshot(piece))
    if diff:
        record("catalog.piece_updated", actor=actor, obj=piece, diff=diff, request=request)
    return piece


def publication_missing(piece: Piece) -> list[str]:
    missing = []
    for field, label in [
        ("category_id", "categoría"),
        ("price_cents", "precio"),
        ("name_es", "nombre en español"),
        ("slug_es", "slug en español"),
        ("short_description_es", "descripción corta en español"),
    ]:
        if not getattr(piece, field):
            missing.append(label)
    if not piece.images.filter(processing_status="ready").exists():
        missing.append("imagen procesada")
    if not piece.images.filter(is_primary=True, processing_status="ready").exists():
        missing.append("imagen principal procesada")
    return missing


@transaction.atomic
def publish_piece(piece: Piece, actor: Actor, request: HttpRequest | None = None) -> Piece:
    piece = Piece.objects.select_for_update().get(pk=piece.pk)
    missing = publication_missing(piece)
    if missing:
        raise PublicationError(str(_("Falta: ")) + ", ".join(missing))
    old = snapshot(piece)
    piece.status = Piece.Status.PUBLISHED
    piece.published_at = piece.published_at or timezone.now()
    piece.save(update_fields=["status", "published_at"])
    if diff := compute_diff(old, snapshot(piece)):
        record("catalog.piece_published", actor=actor, obj=piece, diff=diff, request=request)
    return piece


@transaction.atomic
def hide_pieces(
    queryset: models.QuerySet[Piece], actor: Actor, request: HttpRequest | None = None
) -> None:
    for piece in queryset.select_for_update():
        _set_status(piece, Piece.Status.HIDDEN, "catalog.piece_hidden", actor, request)


def _set_status(
    piece: Piece, status: str, action: str, actor: Actor, request: HttpRequest | None
) -> None:
    old = snapshot(piece)
    piece.status = status
    piece.save(update_fields=["status"])
    if diff := compute_diff(old, snapshot(piece)):
        record(action, actor=actor, obj=piece, diff=diff, request=request)


@transaction.atomic
def archive_piece(piece: Piece, actor: Actor, request: HttpRequest | None = None) -> None:
    piece = Piece.objects.select_for_update().get(pk=piece.pk)
    _set_status(piece, Piece.Status.ARCHIVED, "catalog.piece_archived", actor, request)


@transaction.atomic
def unhide(piece: Piece, actor: Actor, request: HttpRequest | None = None) -> Piece:
    return publish_piece(piece, actor, request)


@transaction.atomic
def delete_piece(piece: Piece) -> None:
    piece = Piece.objects.select_for_update().get(pk=piece.pk)
    piece.delete()


@transaction.atomic
def save_taxonomy(obj: Taxonomy) -> None:
    if (
        hasattr(obj, "cover_image")
        and obj.cover_image
        and not getattr(obj.cover_image, "_committed", True)
    ):
        clean = crop_to_ratio(validated_image(obj.cover_image))
        obj.cover_image.save(f"{uuid4().hex}.webp", encode_webp(clean), save=False)
    obj.full_clean()
    obj.save()


@transaction.atomic
def save_piece_image(obj: PieceImage) -> None:
    from .tasks import process_piece_image

    changed = not getattr(obj.original, "_committed", True)
    if changed:
        clean = validated_image(obj.original)
        obj.original.save(f"{uuid4().hex}.webp", encode_webp(clean), save=False)
        obj.processing_status = PieceImage.ProcessingStatus.PENDING
        obj.error = ""
    obj.full_clean()
    obj.save()
    if changed or obj.processing_status == PieceImage.ProcessingStatus.PENDING:
        transaction.on_commit(lambda: process_piece_image.delay(obj.pk))


@transaction.atomic
def delete_piece_image(obj: PieceImage) -> None:
    obj.delete()


@transaction.atomic
def save_collection_piece(obj: CollectionPiece) -> None:
    obj.full_clean()
    obj.save()


@transaction.atomic
def delete_catalog_object(obj: Taxonomy | CollectionPiece) -> None:
    obj.delete()


@transaction.atomic
def save_piece_relations(piece: Piece, values: dict[str, Any]) -> None:
    for name in ("stones", "materials", "related"):
        if name in values:
            related = values[name]
            if name == "related" and piece.pk in [item.pk for item in related]:
                raise ValidationError(_("Una pieza no puede relacionarse consigo misma."))
            getattr(piece, name).set(related)


@transaction.atomic
def duplicate_piece(piece: Piece, actor: Actor) -> Piece:
    if (
        actor is None
        or not actor.has_perm("catalog.add_piece")
        or not actor.has_perm("catalog.change_piece")
    ):
        raise PermissionDenied
    source = Piece.objects.select_for_update().get(pk=piece.pk)
    # Serialize copies of the same source; bounded identifiers retain room for suffixes.
    index = 1
    while Piece.objects.filter(sku=f"{source.sku[:25]}-COPIA-{index}").exists():
        index += 1
    suffix = f"-copia-{index}"
    data = {
        field.attname: getattr(source, field.attname)
        for field in Piece._meta.concrete_fields
        if not field.primary_key
        and field.name
        not in {
            "sku",
            "piece_number",
            "status",
            "sale_state",
            "published_at",
            "sold_at",
            "name",
            "name_es",
            "name_en",
            "slug",
            "slug_es",
            "slug_en",
        }
    }
    data["sku"] = f"{source.sku[:25]}-COPIA-{index}"
    for locale in ("es", "en"):
        data[f"name_{locale}"] = (
            f"{(getattr(source, f'name_{locale}') or source.name_es)[:192]} (copia)"
        )
        base = getattr(source, f"slug_{locale}") or source.slug_es or source.sku.lower()
        slug = base[:190] + suffix
        collision = 1
        while Piece.objects.filter(**{f"slug_{locale}": slug}).exists():
            collision += 1
            slug = f"{base[:180]}{suffix}-{collision}"
        data[f"slug_{locale}"] = slug
    copy = Piece.objects.create(**data)
    copy.stones.set(source.stones.all())
    copy.materials.set(source.materials.all())
    for link in CollectionPiece.objects.filter(piece=source):
        CollectionPiece.objects.create(
            piece=copy, collection=link.collection, position=link.position
        )
    record("catalog.piece_duplicated", actor=actor, obj=copy, diff={"source": [None, source.pk]})
    return copy
