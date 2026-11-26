from __future__ import annotations

import unicodedata
from datetime import datetime
from typing import Any, cast
from uuid import uuid4
from zlib import crc32

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.db import IntegrityError, connection, models, transaction
from django.http import HttpRequest
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.audit.diff import compute_diff
from apps.audit.services import record
from apps.core.exceptions import PublicationError

from .image_cleanup import batch_file_cleanup
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


# Archived pieces are terminal, including for superusers.
EDITORIAL_TRANSITIONS: dict[str, frozenset[str]] = {
    Piece.Status.DRAFT: frozenset({Piece.Status.PUBLISHED, Piece.Status.ARCHIVED}),
    Piece.Status.PUBLISHED: frozenset({Piece.Status.HIDDEN, Piece.Status.ARCHIVED}),
    Piece.Status.HIDDEN: frozenset({Piece.Status.PUBLISHED, Piece.Status.ARCHIVED}),
    Piece.Status.ARCHIVED: frozenset(),
}


def validate_editorial_transition(source: str, target: str) -> None:
    if target not in EDITORIAL_TRANSITIONS.get(source, ()):
        raise ValidationError(_("No se permite ese cambio de estado de publicación."))


def require_commercial_permission(actor: Actor) -> None:
    if actor is not None and not (
        actor.has_perm("catalog.publish_piece") and actor.has_perm("catalog.change_piece")
    ):
        raise PermissionDenied(_("No tienes permiso para tomar decisiones comerciales."))


def deletion_reasons(piece: Piece) -> list[str]:
    reasons = []
    if piece.status != Piece.Status.DRAFT:
        reasons.append("no es borrador")
    if piece.sale_state in (Piece.SaleState.SOLD, Piece.SaleState.RESERVED):
        reasons.append("está vendida o reservada")
    if (
        piece.deletion_reservations
        if hasattr(piece, "deletion_reservations")
        else piece.reservations.exists()
    ):
        reasons.append("tiene reservas")
    if (
        piece.deletion_status_changes
        if hasattr(piece, "deletion_status_changes")
        else piece.status_changes.exists()
    ):
        reasons.append("tiene historial de inventario")
    if (
        piece.deletion_orderitem_set
        if hasattr(piece, "deletion_orderitem_set")
        else piece.orderitem_set.exists()
    ):
        reasons.append("tiene pedidos")
    return reasons


@transaction.atomic
@batch_file_cleanup()
def delete_pieces(
    queryset: models.QuerySet[Piece], *, actor: Actor = None, request: HttpRequest | None = None
) -> None:
    pieces = list(queryset.order_by("pk").select_for_update(of=("self",)))
    failures = [
        f"{piece.sku} ({', '.join(reasons)})"
        for piece in pieces
        if (reasons := deletion_reasons(piece))
    ]
    if failures:
        raise ValidationError("No se borró ninguna pieza: " + "; ".join(failures))
    for piece in pieces:
        record(
            "catalog.piece_deleted",
            actor=actor,
            obj=piece,
            diff={"Pieza": [piece.name_es, None], "SKU": [piece.sku, None]},
            request=request,
        )
        piece.delete()


def hard_delete_blockers(piece: Piece) -> list[str]:
    """Pending online and manual payments are the non-final payment states."""
    reasons: list[str] = []
    if (
        hasattr(piece, "hard_delete_active_reservation")
        and hasattr(piece, "hard_delete_pending_order")
        and not piece.hard_delete_active_reservation
        and not piece.hard_delete_pending_order
    ):
        return reasons
    for reservation in piece.reservations.filter(status="active").select_related("order"):
        reasons.append(
            f"Reserva activa ({reservation.order or reservation.reference or 'sin pedido'})"
        )
    for item in piece.orderitem_set.filter(
        order__payment_status__in=("pending", "awaiting_manual_payment")
    ).select_related("order"):
        reasons.append(f"Pedido pendiente {item.order}")
    return reasons


def _preserve_order_images(piece: Piece) -> None:
    from pathlib import PurePosixPath

    from apps.catalog.image_cleanup import file_paths
    from apps.orders.models import OrderItem

    paths = set().union(*(file_paths(image) for image in piece.images.all()))
    urls = {path: default_storage.url(path) for path in paths}
    for item in piece.orderitem_set.all():
        replacements = {}
        for path, url in urls.items():
            if (
                path not in str(item.image_snapshot)
                and url not in str(item.image_snapshot)
                and path not in item.image_path
                and url not in item.image_path
            ):
                continue
            if not default_storage.exists(path):
                raise ValidationError(f"No se encuentra la imagen histórica: {path}")
            target = (
                f"orders/snapshots/{item.order_id}/{item.pk}/"
                f"{uuid4().hex}{PurePosixPath(path).suffix}"
            )
            with default_storage.open(path, "rb") as source:
                target = default_storage.save(target, source)
            replacements[path] = target
            replacements[url] = default_storage.url(target)

        def replace(value, replacements=replacements):
            if isinstance(value, str):
                for old in sorted(replacements, key=len, reverse=True):
                    value = value.replace(old, replacements[old])
                return value
            if isinstance(value, dict):
                return {key: replace(child) for key, child in value.items()}
            if isinstance(value, list):
                return [replace(child) for child in value]
            return value

        if replacements:
            # Exception to immutable snapshots: only relocate image references, never order data.
            models.QuerySet(model=OrderItem, using=item._state.db).filter(pk=item.pk).update(
                image_path=replace(item.image_path), image_snapshot=replace(item.image_snapshot)
            )


@transaction.atomic
@batch_file_cleanup()
def hard_delete_pieces(
    queryset: models.QuerySet[Piece], *, actor: Actor, request: HttpRequest | None = None
) -> None:
    from apps.cms.documents import lock_document
    from apps.cms.redirects import _apply_automatic_transitions
    from apps.core.routes import href

    if actor is None or not actor.has_perm("catalog.delete_piece"):
        raise PermissionDenied
    require_commercial_permission(actor)
    lock_document("home")
    pieces = list(queryset.order_by("pk").select_for_update(of=("self",)))
    failures = [
        f"{p.sku} ({', '.join(reasons)})" for p in pieces if (reasons := hard_delete_blockers(p))
    ]
    if failures:
        raise ValidationError("No se borró ninguna pieza: " + "; ".join(failures))
    for piece in pieces:
        _preserve_order_images(piece)
        data = snapshot(piece)
        data.update(
            {
                "collections": list(piece.collections.values_list("name_es", flat=True)),
                "stones": list(piece.stones.values_list("name_es", flat=True)),
                "materials": list(piece.materials.values_list("name_es", flat=True)),
                "order_count": piece.orderitem_set.values("order_id").distinct().count(),
            }
        )
        record(
            "catalog.piece_deleted",
            actor=actor,
            obj=piece,
            diff={key: [value, None] for key, value in data.items()},
            request=request,
        )
        transitions = []
        for lang in ("es", "en"):
            try:
                transitions.append(
                    (
                        lang,
                        href("piece", lang, piece),
                        href("category", lang, piece.category)
                        if piece.category_id
                        else href("catalog", lang),
                    )
                )
            except ValueError:
                continue
        if transitions:
            _apply_automatic_transitions(transitions, actor)
        piece.delete(_hard_delete=True)


def hard_delete_piece(piece: Piece, *, actor: Actor, request: HttpRequest | None = None) -> None:
    hard_delete_pieces(Piece.objects.filter(pk=piece.pk), actor=actor, request=request)


def snapshot(piece: Piece) -> dict[str, object]:
    return {
        field.name: (
            getattr(piece, field.attname).isoformat()
            if isinstance(getattr(piece, field.attname), datetime)
            else (cast(Category, piece.category).name_es if piece.category_id else None)
            if field.name == "category"
            else getattr(piece, field.attname)
        )
        for field in piece._meta.concrete_fields
        if not isinstance(field, models.FileField)
    }


def next_piece_sku(piece: Piece) -> str:
    category = piece.category
    if category and category.parent_id:
        category = category.parent
    name = category.name_es if category else "GEN"
    letters = "".join(c for c in unicodedata.normalize("NFKD", name) if c.isascii() and c.isalpha())
    prefix = f"SRT-{(letters.upper()[:3] or 'GEN')}-"
    if connection.vendor == "postgresql":
        # Transaction-level lock also works when this prefix has no pieces yet.
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(%s, %s)", [7319, crc32(prefix.encode()) % 2147483647]
            )
    numbers = [
        int(sku[len(prefix) :])
        for sku in Piece.objects.filter(sku__startswith=prefix).values_list("sku", flat=True)
        if sku[len(prefix) :].isdigit()
    ]
    return f"{prefix}{max(numbers, default=0) + 1:04d}"


@transaction.atomic
def save_piece(piece: Piece, *, actor: Actor, request: HttpRequest | None = None) -> Piece:
    # Serialize automatic redirects with editorial and manual redirect changes.
    from apps.cms.documents import lock_document
    from apps.cms.redirects import on_piece_slug_change

    # Only a published piece changing its address touches redirects: lock the editorial
    # document first (same order as page publications) and only then, so ordinary edits
    # don't serialize with the CMS.
    stored = (
        Piece.objects.filter(pk=piece.pk).values("status", "slug_es", "slug_en").first()
        if piece.pk
        else None
    )
    if (
        stored
        and stored["status"] == Piece.Status.PUBLISHED
        and (stored["slug_es"], stored["slug_en"]) != (piece.slug_es, piece.slug_en)
    ):
        lock_document("home")
    old = (
        Piece.objects.select_for_update(of=("self",)).filter(pk=piece.pk).first()
        if piece.pk
        else None
    )
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
    automatic_sku = not piece.sku
    # Historical unknown keys survive edits, but cannot be introduced or altered here.
    from .validators import ATTRIBUTE_FIELDS, validate_attributes

    attributes = piece.attributes
    if not isinstance(attributes, dict):
        validate_attributes(attributes)
    unknown = {k: v for k, v in attributes.items() if k not in ATTRIBUTE_FIELDS}
    previous_unknown = {
        k: v for k, v in (old.attributes if old else {}).items() if k not in ATTRIBUTE_FIELDS
    }
    if unknown != previous_unknown:
        raise ValidationError({"attributes": "Los atributos contienen claves no permitidas."})
    validate_attributes({k: v for k, v in attributes.items() if k in ATTRIBUTE_FIELDS})
    for attempt in range(5):
        if automatic_sku:
            piece.sku = next_piece_sku(piece)
        try:
            piece.full_clean(exclude=["attributes"])
            with transaction.atomic():
                piece.save()
            break
        except ValidationError as exc:
            if not (
                automatic_sku and attempt < 4 and set(getattr(exc, "error_dict", {})) == {"sku"}
            ):
                raise
        except IntegrityError:
            if (
                not automatic_sku
                or attempt == 4
                or not Piece.objects.filter(sku=piece.sku).exists()
            ):
                raise
    if old and old.status == Piece.Status.PUBLISHED:
        on_piece_slug_change(old, piece, actor, request)
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
        ("slug_es", "dirección web en español"),
        ("short_description_es", "descripción corta en español"),
    ]:
        if not getattr(piece, field):
            missing.append(label)
    if not piece.pk:
        return [*missing, "al menos una foto lista", "foto principal lista"]
    photos = list(piece.images.all())  # reuse the admin's prefetch, including photos/status
    primary_pending = any(p.is_primary and p.processing_status == "pending" for p in photos)
    if primary_pending:
        missing.append("la foto principal aún se está procesando")
    else:
        if not any(p.processing_status == "ready" for p in photos):
            missing.append("al menos una foto lista")
        if not any(p.is_primary and p.processing_status == "ready" for p in photos):
            missing.append("foto principal lista")
    return missing


@transaction.atomic
def publish_piece(piece: Piece, actor: Actor, request: HttpRequest | None = None) -> Piece:
    piece = Piece.objects.select_for_update(of=("self",)).get(pk=piece.pk)
    require_commercial_permission(actor)
    validate_editorial_transition(piece.status, Piece.Status.PUBLISHED)
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
    for piece in queryset.select_for_update(of=("self",)):
        _set_status(piece, Piece.Status.HIDDEN, "catalog.piece_hidden", actor, request)


def _set_status(
    piece: Piece, status: str, action: str, actor: Actor, request: HttpRequest | None
) -> None:
    require_commercial_permission(actor)
    validate_editorial_transition(piece.status, status)
    old = snapshot(piece)
    piece.status = status
    piece.save(update_fields=["status"])
    if diff := compute_diff(old, snapshot(piece)):
        record(action, actor=actor, obj=piece, diff=diff, request=request)


@transaction.atomic
def archive_piece(piece: Piece, actor: Actor, request: HttpRequest | None = None) -> None:
    piece = Piece.objects.select_for_update(of=("self",)).get(pk=piece.pk)
    _set_status(piece, Piece.Status.ARCHIVED, "catalog.piece_archived", actor, request)


@transaction.atomic
def unhide(piece: Piece, actor: Actor, request: HttpRequest | None = None) -> Piece:
    piece = Piece.objects.select_for_update(of=("self",)).get(pk=piece.pk)
    require_commercial_permission(actor)
    if piece.status != Piece.Status.HIDDEN:
        raise ValidationError(_("Solo se pueden volver a publicar piezas ocultas."))
    return publish_piece(piece, actor, request)


@transaction.atomic
def delete_piece(piece: Piece, *, actor: Actor = None, request: HttpRequest | None = None) -> None:
    delete_pieces(Piece.objects.filter(pk=piece.pk), actor=actor, request=request)


@transaction.atomic
def save_taxonomy(
    obj: Taxonomy, *, actor: Actor = None, request: HttpRequest | None = None
) -> None:
    old = (
        type(obj).objects.select_for_update(of=("self",)).filter(pk=obj.pk).first()
        if obj.pk
        else None
    )
    before = taxonomy_snapshot(old) if old else {}
    if (
        isinstance(obj, (Category, Collection, Stone))
        and obj.cover_image
        and not getattr(obj.cover_image, "_committed", True)
    ):
        image = validated_image(obj.cover_image)
        # Stone/category covers fill tall cards and a wide banner (object-fit: cover),
        # so they keep the photo's own shape; other covers stay 16:9.
        clean = cap_master(image if isinstance(obj, (Stone, Category)) else crop_to_ratio(image))
        obj.cover_width, obj.cover_height = clean.size
        obj.cover_renditions = {
            "webp": build_renditions(clean, f"catalog/renditions/{uuid4().hex}")
        }
        obj.cover_image.save(f"{uuid4().hex}.webp", encode_webp(clean), save=False)
    if isinstance(obj, (Category, Collection, Stone)) and not obj.cover_image:
        obj.cover_renditions, obj.cover_width, obj.cover_height = {}, 0, 0
    if isinstance(obj, Category):
        from django.utils.text import slugify

        if old is None:
            last = Category.objects.filter(parent_id=obj.parent_id).aggregate(
                last=models.Max("position")
            )["last"]
            obj.position = last + 1 if last is not None else 0

        duplicate = Category.objects.filter(
            parent_id=obj.parent_id, name_es__iexact=obj.name_es.strip()
        ).exclude(pk=obj.pk)
        if duplicate.exists():
            location = (
                f" dentro de {cast(Category, obj.parent).name_es}"
                if obj.parent_id
                else " entre las categorías principales"
            )
            raise ValidationError({"name_es": f"Ya existe «{obj.name_es}»{location}."})
        if not obj.slug_es:
            base = slugify(obj.name_es) or "categoria"
            candidate, suffix = base, 2
            while Category.objects.filter(slug_es=candidate).exclude(pk=obj.pk).exists():
                candidate = f"{base}-{suffix}"
                suffix += 1
            obj.slug_es = candidate
    obj.full_clean()
    obj.save()
    diff = compute_diff(before, taxonomy_snapshot(obj))
    # Presence alone cannot distinguish replacement of two existing covers.
    if (
        old
        and hasattr(obj, "cover_image")
        and cast(Any, old).cover_image.name != cast(Any, obj).cover_image.name
    ):
        diff.pop("Portada", None)
        diff[f"Portada de {obj.name_es}"] = [
            "Portada anterior" if cast(Any, old).cover_image else "Sin portada",
            "Portada reemplazada"
            if cast(Any, old).cover_image and cast(Any, obj).cover_image
            else "Portada añadida"
            if cast(Any, obj).cover_image
            else "Sin portada",
        ]
    if diff:
        action = f"catalog.{obj._meta.model_name}_{'updated' if old else 'created'}"
        record(action, actor=actor, obj=obj, diff=diff, request=request)


def taxonomy_snapshot(obj: Taxonomy) -> dict[str, object]:
    result = {}
    for field in obj._meta.concrete_fields:
        if field.primary_key or field.name in {
            "name",
            "slug",
            "description",
            "seo_title",
            "seo_description",
            "updated_at",  # bookkeeping timestamp, not an editorial change
        }:
            continue  # translated originals alias the active language
        if field.name.startswith("cover_"):
            continue
        value = getattr(obj, field.name)
        if field.is_relation:
            value = value.name_es if value else None
        result[str(field.verbose_name)] = value
    if hasattr(obj, "cover_image"):
        result["Portada"] = "Con portada" if obj.cover_image else "Sin portada"
    return result


@transaction.atomic
def save_piece_image(obj: PieceImage) -> None:
    from .tasks import process_piece_image

    changed = not getattr(obj.original, "_committed", True)
    is_new = obj.pk is None
    if changed:
        clean = cap_master(validated_image(obj.original))
        obj.original.save(f"{uuid4().hex}.webp", encode_webp(clean), save=False)
        obj.renditions = {}
        obj.processing_status = PieceImage.ProcessingStatus.PENDING
        obj.error = ""
    obj.full_clean()
    obj.save()
    if changed or (is_new and obj.processing_status == PieceImage.ProcessingStatus.PENDING):
        transaction.on_commit(lambda: process_piece_image.delay(obj.pk))


PUBLISHED_PHOTO_MESSAGE = (
    "Esta pieza está publicada: elige como principal una foto que ya esté lista, "
    "u oculta la pieza antes de cambiarla."
)


def validate_photo_state(piece: Piece, photos: list[PieceImage]) -> None:
    primary = [photo for photo in photos if photo.is_primary]
    if piece.status == Piece.Status.PUBLISHED and (
        len(primary) != 1
        or primary[0].processing_status != "ready"
        or not getattr(primary[0].original, "_committed", True)
    ):
        raise ValidationError(PUBLISHED_PHOTO_MESSAGE)
    if sum(photo.is_hover for photo in photos) > 1:
        raise ValidationError("Selecciona solo una imagen al pasar el cursor por pieza.")
    if photos and len(primary) != 1:
        raise ValidationError("Selecciona exactamente una foto principal.")
    if any(photo.is_primary and photo.is_hover for photo in photos):
        raise ValidationError("Una imagen no puede ser principal y al pasar el cursor a la vez.")
    positions = [photo.position for photo in photos]
    if len(set(positions)) != len(positions):
        raise ValidationError("Cada foto debe tener una posición diferente.")


@transaction.atomic
@batch_file_cleanup()
def apply_photo_changes(
    piece: Piece, photos: list[PieceImage], *, actor: Actor, request: HttpRequest | None = None
) -> None:
    """Replace the complete inline state, with immediate PostgreSQL constraints in mind."""
    piece = Piece.objects.select_for_update(of=("self",)).get(pk=piece.pk)
    if actor is not None and not actor.has_perm("catalog.change_piece"):
        raise PermissionDenied("No tienes permiso para editar esta pieza.")
    current = {p.pk: p for p in piece.images.select_for_update(of=("self",))}
    ids = [p.pk for p in photos if p.pk is not None]
    if len(set(ids)) != len(ids) or any(pk not in current for pk in ids):
        raise ValidationError("Las fotos cambiaron. Recarga la página e inténtalo de nuevo.")
    deleted = set(current) - set(ids)
    if deleted and actor is not None and not actor.has_perm("catalog.delete_pieceimage"):
        raise ValidationError("No tienes permiso para borrar fotos.")
    # The worker may have completed since the form was loaded. Preserve its fields.
    for photo in photos:
        if photo.pk:
            old = current[photo.pk]
            for field in ("processing_status", "error", "renditions", "width", "height"):
                setattr(photo, field, getattr(old, field))
        photo.piece = piece
    validate_photo_state(piece, photos)
    ordered = sorted(photos, key=lambda p: p.position)

    def state(rows: list[PieceImage]) -> dict[str, object]:
        return {
            "principal": next((p.pk for p in rows if p.is_primary), None),
            "hover": next((p.pk for p in rows if p.is_hover), None),
            "orden": [p.pk for p in sorted(rows, key=lambda p: p.position)],
        }

    before = state(list(current.values()))
    labels = {
        p.pk: f"Foto {p.position + 1}: {p.alt_es or 'Sin descripción'}" for p in current.values()
    }
    alt_before = {p.pk: (p.alt_es, p.alt_en) for p in current.values()}
    original_before = {p.pk: p.original.name for p in current.values()}
    # Find a free block above the final range, including legacy positions near int32's limit.
    offset = len(photos)
    for position in sorted(p.position for p in current.values()):
        if position >= offset and position < offset + len(current):
            offset = position + 1
    if offset + len(current) > 2_147_483_647:
        raise ValidationError("No se pudo ordenar las fotos. Revisa sus posiciones.")
    piece.images.update(is_primary=False, is_hover=False)
    for index, pk in enumerate(current):
        piece.images.filter(pk=pk).update(position=offset + index)
    for pk in deleted:
        delete_piece_image(current[pk])  # Existing signals clean files after commit.
    for index, photo in enumerate(ordered):
        photo.position = index
        save_piece_image(photo)
    after = state(ordered)
    diff = {key: [before[key], after[key]] for key in before if before[key] != after[key]}
    if deleted:
        diff["borradas"] = [sorted(deleted), []]
    for photo in ordered:
        labels.setdefault(
            photo.pk, f"Foto {photo.position + 1}: {photo.alt_es or 'Sin descripción'}"
        )
        if photo.pk in alt_before:
            for index, locale in enumerate(("es", "en")):
                previous, value = alt_before[photo.pk][index], getattr(photo, f"alt_{locale}")
                if previous != value:
                    diff[f"Descripción de {labels[photo.pk]} ({locale})"] = [previous, value]
            if original_before[photo.pk] != photo.original.name:
                diff[f"Archivo de {labels[photo.pk]}"] = ["Foto anterior", "Foto reemplazada"]
    for key in ("principal", "hover", "orden", "borradas"):
        if key in diff:
            diff[key] = [
                [labels[pk] for pk in value]
                if isinstance(value, list)
                else labels.get(cast(int, value))
                for value in diff[key]
            ]
    if diff:
        record("catalog.photos_updated", actor=actor, obj=piece, diff=diff, request=request)


@transaction.atomic
def retry_piece_image(piece: Piece, image_id: int) -> None:
    from django.shortcuts import get_object_or_404

    from .tasks import process_piece_image

    Piece.objects.select_for_update(of=("self",)).get(pk=piece.pk)
    image = get_object_or_404(
        PieceImage.objects.select_for_update(of=("self",)), pk=image_id, piece_id=piece.pk
    )
    if image.processing_status == "failed":
        image.processing_status, image.error = "pending", ""
        image.save(update_fields=["processing_status", "error"])
        transaction.on_commit(lambda: process_piece_image.delay(image.pk))


@transaction.atomic
def delete_piece_image(obj: PieceImage) -> None:
    obj.delete()


def collection_names(piece: Piece) -> list[str]:
    return list(piece.collections.order_by("name_es", "pk").values_list("name_es", flat=True))


def record_collections(
    piece: Piece,
    before: list[str],
    *,
    actor: Actor,
    request: HttpRequest | None,
    extra_diff: dict[str, list[object]] | None = None,
) -> None:
    after = collection_names(piece)
    diff = dict(extra_diff or {})
    if before != after:
        diff["Colecciones"] = [before, after]
    if diff:
        record(
            "catalog.collections_updated",
            actor=actor,
            obj=piece,
            diff=diff,
            request=request,
        )


@transaction.atomic
def save_collection_piece(
    obj: CollectionPiece, *, actor: Actor = None, request: HttpRequest | None = None
) -> None:
    piece = Piece.objects.select_for_update(of=("self",)).get(pk=obj.piece_id)
    before = collection_names(piece)
    old = (
        CollectionPiece.objects.select_related("collection").filter(pk=obj.pk).first()
        if obj.pk
        else None
    )
    obj.full_clean()
    obj.save()
    extra_diff: dict[str, list[object]] = {}
    if old and old.position != obj.position:
        extra_diff[f"Posición en {obj.collection.name_es}"] = [old.position, obj.position]
    record_collections(piece, before, actor=actor, request=request, extra_diff=extra_diff)


@transaction.atomic
def replace_piece_collection(
    piece: Piece,
    old: Collection,
    new: Collection | None,
    *,
    actor: Actor,
    request: HttpRequest | None = None,
) -> None:
    piece = Piece.objects.select_for_update(of=("self",)).get(pk=piece.pk)
    before = collection_names(piece)
    CollectionPiece.objects.filter(piece=piece, collection=old).delete()
    if new is not None:
        CollectionPiece.objects.get_or_create(piece=piece, collection=new)
    record_collections(piece, before, actor=actor, request=request)


def taxonomy_blocking_pieces(obj: Category | Stone | Collection) -> models.QuerySet[Piece]:
    return obj.pieces.order_by("sku")


def taxonomy_blocking_children(obj: Category) -> models.QuerySet[Category]:
    return obj.children.order_by("name_es", "pk")


def taxonomy_deletion_reason(obj) -> str:
    if isinstance(obj, Category):
        if (
            obj.deletion_child_count
            if hasattr(obj, "deletion_child_count")
            else obj.children.exists()
        ):
            return "Tiene subcategorías"
        count = (
            obj.deletion_piece_count if hasattr(obj, "deletion_piece_count") else obj.pieces.count()
        )
        if count:
            return (
                "Tiene 1 pieza: muévela antes de eliminarla"
                if count == 1
                else f"Tiene {count} piezas: muévelas antes de eliminarla"
            )
    if isinstance(obj, (Stone, Collection)):
        count = (
            obj.deletion_piece_count if hasattr(obj, "deletion_piece_count") else obj.pieces.count()
        )
        if count:
            return (
                "Tiene 1 pieza: retírala antes de eliminarla"
                if count == 1
                else f"Tiene {count} piezas: retíralas antes de eliminarla"
            )
    return ""


@transaction.atomic
def delete_catalog_object(
    obj: Taxonomy | CollectionPiece | PieceVideo,
    *,
    actor: Actor = None,
    request: HttpRequest | None = None,
) -> None:
    if isinstance(obj, (Category, Stone, Collection, Material)):
        locked = type(obj).objects.select_for_update(of=("self",)).get(pk=obj.pk)
        if reason := taxonomy_deletion_reason(locked):
            raise ValidationError(reason)
    if isinstance(obj, CollectionPiece):
        piece = Piece.objects.select_for_update(of=("self",)).get(pk=obj.piece_id)
        before = collection_names(piece)
        obj.delete()
        record_collections(piece, before, actor=actor, request=request)
    else:
        if isinstance(obj, (Category, Collection, Stone, Material)):
            record(
                f"catalog.{obj._meta.model_name}_deleted",
                actor=actor,
                obj=obj,
                diff={key: [value, None] for key, value in taxonomy_snapshot(obj).items()},
                request=request,
            )
        obj.delete()


@transaction.atomic
def save_piece_relations(
    piece: Piece, values: dict[str, Any], *, actor: Actor = None, request: HttpRequest | None = None
) -> None:
    Piece.objects.select_for_update(of=("self",)).get(pk=piece.pk)
    diff: dict[str, list[object]] = {}
    for name, label in (
        ("stones", "Piedras"),
        ("materials", "Materiales"),
        ("related", "Piezas relacionadas"),
    ):
        if name in values:
            related = list(values[name])
            if name == "related" and piece.pk in [item.pk for item in related]:
                raise ValidationError(_("Una pieza no puede relacionarse consigo misma."))
            manager = getattr(piece, name)
            before = list(manager.order_by("name_es", "pk").values_list("name_es", flat=True))
            manager.set(related)
            after = list(manager.order_by("name_es", "pk").values_list("name_es", flat=True))
            if before != after:
                diff[label] = [before, after]
    if diff:
        record("catalog.relations_updated", actor=actor, obj=piece, diff=diff, request=request)


@transaction.atomic
def duplicate_piece(piece: Piece, actor: Actor, request: HttpRequest | None = None) -> Piece:
    if (
        actor is None
        or not actor.has_perm("catalog.add_piece")
        or not actor.has_perm("catalog.change_piece")
    ):
        raise PermissionDenied
    require_commercial_permission(actor)
    source = Piece.objects.select_for_update(of=("self",)).get(pk=piece.pk)
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
    data["sku"] = ""
    for locale in ("es", "en"):
        data[f"name_{locale}"] = (
            f"{(getattr(source, f'name_{locale}') or source.name_es)[:192]} (copia)"
        )
    copy = Piece(**data)
    copy.sku = next_piece_sku(copy)
    copy.save()
    copy.stones.set(source.stones.all())
    copy.materials.set(source.materials.all())
    for link in CollectionPiece.objects.filter(piece=source):
        CollectionPiece.objects.create(
            piece=copy, collection=link.collection, position=link.position
        )
    record(
        "catalog.piece_duplicated",
        actor=actor,
        obj=copy,
        diff={"source": [None, f"{source.name_es} ({source.sku})"]},
        request=request,
    )
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
@batch_file_cleanup()
def append_piece_photos(
    piece: Piece, uploads: list[Any], *, actor: Actor = None, request: HttpRequest | None = None
) -> list[str]:
    """Validate each upload independently while serializing ordering and primary selection."""
    piece = Piece.objects.select_for_update(of=("self",)).get(pk=piece.pk)
    position = piece.images.count()
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
                current = list(piece.images.all())
                for index, photo in enumerate(current):
                    photo.position = index
                apply_photo_changes(piece, [*current, image], actor=actor, request=request)
        except ValidationError as exc:
            errors.append(f"{upload.name}: {'; '.join(exc.messages)}")
        else:
            position += 1
            primary = False
    return errors
