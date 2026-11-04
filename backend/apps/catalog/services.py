from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.db import models, transaction
from django.http import HttpRequest
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.audit.diff import compute_diff
from apps.audit.services import record
from apps.core.exceptions import PublicationError

from .images import (
    build_renditions,
    cap_master,
    crop_to_ratio,
    encode_webp,
    rendition_widths,
    validated_image,
)
from .models import (
    Category,
    Collection,
    CollectionPiece,
    Material,
    Piece,
    PieceImage,
    PieceVideo,
    Stone,
)

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
        isinstance(obj, (Category, Collection, Stone))
        and obj.cover_image
        and not getattr(obj.cover_image, "_committed", True)
    ):
        image = validated_image(obj.cover_image)
        # Stone covers fill tall home panels and a wide page banner (both object-fit: cover),
        # so they keep the photo's own shape; other covers stay 16:9.
        clean = cap_master(image if isinstance(obj, Stone) else crop_to_ratio(image))
        obj.cover_width, obj.cover_height = clean.size
        obj.cover_renditions = {
            "webp": build_renditions(clean, f"catalog/renditions/{uuid4().hex}")
        }
        obj.cover_image.save(f"{uuid4().hex}.webp", encode_webp(clean), save=False)
    if isinstance(obj, (Category, Collection, Stone)) and not obj.cover_image:
        obj.cover_renditions, obj.cover_width, obj.cover_height = {}, 0, 0
    obj.full_clean()
    obj.save()


@transaction.atomic
def save_piece_image(obj: PieceImage) -> None:
    from .tasks import process_piece_image

    changed = not getattr(obj.original, "_committed", True)
    if changed:
        clean = cap_master(validated_image(obj.original))
        obj.original.save(f"{uuid4().hex}.webp", encode_webp(clean), save=False)
        obj.renditions = {}
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
def delete_catalog_object(obj: Taxonomy | CollectionPiece | PieceVideo) -> None:
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


@transaction.atomic
def rebuild_image(
    obj: Category | Collection | Stone | PieceImage | models.Model, *, dry_run: bool
) -> bool:
    """Repair legacy images through the service layer; return whether work was needed."""
    from apps.cms.models import HomeSection, PersonalizationService
    from apps.cms.services import process_image

    from .tasks import process_piece_image

    obj = type(obj)._default_manager.select_for_update().get(pk=obj.pk)
    if isinstance(obj, PieceImage):
        field = obj.original
        paths = obj.renditions
    elif isinstance(obj, (Category, Collection, Stone)):
        field = obj.cover_image
        paths = obj.cover_renditions
    elif isinstance(obj, (HomeSection, PersonalizationService)):
        field = obj.image
        paths = obj.renditions
    else:
        return False
    if not field:
        return False
    with field.open("rb") as source:
        image = validated_image(source)
    oversized = max(image.size) > 2400
    widths = (
        (960, 1600, 2400)
        if isinstance(obj, (HomeSection, PersonalizationService))
        else (480, 960, 1600, 2400)
    )
    expected = {str(width) for width in rendition_widths(image.width, widths)}
    existing = paths.get("webp", {})
    if (
        not oversized
        and expected == set(existing)
        and all(default_storage.exists(path) for path in existing.values())
    ):
        return False
    if dry_run:
        return True
    if isinstance(obj, PieceImage):
        if oversized:
            image = cap_master(image)
            obj.original.save(f"{uuid4().hex}.webp", encode_webp(image), save=False)
            obj.save(update_fields=["original"])
        process_piece_image(obj.pk)
        obj.refresh_from_db()
        if obj.processing_status != PieceImage.ProcessingStatus.READY:
            raise ValidationError(_("No se pudo procesar la imagen."))
    elif isinstance(obj, (Category, Collection, Stone)):
        obj.cover_image = encode_webp(image)
        obj.cover_image.name = "rebuild.webp"
        save_taxonomy(obj)
    elif isinstance(obj, (HomeSection, PersonalizationService)):
        obj.image = encode_webp(image)
        obj.image.name = "rebuild.webp"
        process_image(obj)
        obj.save(update_fields=["image", "renditions", "width", "height"])
    return True


@transaction.atomic
def save_piece_video(obj: PieceVideo) -> None:
    from .tasks import process_piece_video
    from .videos import validate_video

    # Serialize upload replacements with in-flight processing.
    if obj.pk:
        type(obj).objects.select_for_update().get(pk=obj.pk)
    changed = bool(obj.original) and not getattr(obj.original, "_committed", True)
    if changed:
        validate_video(obj.original)
        obj.mp4, obj.poster, obj.poster_renditions = "", "", {}
        obj.width, obj.height, obj.duration_seconds = 0, 0, 0
        obj.processing_status, obj.error = "pending", ""
    if not obj.original and obj.processing_status != "ready":
        raise ValidationError(_("Selecciona un video."))
    obj.full_clean()
    obj.save()
    if changed or obj.processing_status == "pending":
        transaction.on_commit(lambda: process_piece_video.delay(obj.pk))


@transaction.atomic
def append_piece_photos(piece: Piece, uploads: list[Any]) -> list[str]:
    """Validate each upload independently while serializing ordering and primary selection."""
    Piece.objects.select_for_update().get(pk=piece.pk)
    position = max(piece.images.values_list("position", flat=True), default=-1) + 1
    primary = not piece.images.filter(is_primary=True).exists()
    errors = []
    for upload in uploads:
        try:
            with transaction.atomic():
                validated_image(upload)
                image = PieceImage(
                    piece=piece,
                    original=upload,
                    position=position,
                    alt_es=piece.name_es,
                    alt_en=piece.name_en or piece.name_es,
                    is_primary=primary,
                )
                save_piece_image(image)
        except ValidationError as exc:
            errors.append(f"{upload.name}: {'; '.join(exc.messages)}")
        else:
            position += 1
            primary = False
    return errors
