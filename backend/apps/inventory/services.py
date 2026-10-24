from datetime import datetime

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.catalog.models import Piece
from apps.core.exceptions import DomainError

from .models import PieceReservation, PieceStatusChange


class PieceNotAvailable(DomainError):
    status_code = 409

    def __init__(self, *, state: str) -> None:
        self.state = state
        self.default_code = f"piece_{state}"
        super().__init__(str(_("La pieza no está disponible.")), code=self.default_code)


def _transition(
    piece: Piece,
    to_state: str,
    *,
    reason: str,
    ref: str = "",
    actor: User | AnonymousUser | None = None,
) -> None:
    if reason not in PieceStatusChange.Reason.values:
        raise ValidationError(_("Motivo de cambio inválido."))
    if piece.sale_state == Piece.SaleState.SOLD:
        raise PieceNotAvailable(state=piece.sale_state)
    previous = piece.sale_state
    piece.sale_state = to_state
    if to_state == Piece.SaleState.SOLD:
        piece.sold_at = timezone.now()
    piece.save(update_fields=["sale_state", "sold_at"])
    PieceStatusChange.objects.create(
        piece=piece,
        from_state=previous,
        to_state=to_state,
        reason=reason,
        ref=ref,
        actor=actor if isinstance(actor, User) else None,
    )


@transaction.atomic
def reserve_piece(
    piece_id: int, *, kind: str, reference: str, expires_at: datetime
) -> PieceReservation:
    piece = Piece.objects.select_for_update().get(pk=piece_id)
    if piece.sale_state != Piece.SaleState.AVAILABLE:
        raise PieceNotAvailable(state=piece.sale_state)
    reservation = PieceReservation(
        piece=piece, kind=kind, reference=reference, expires_at=expires_at
    )
    reservation.full_clean()
    reservation.save()
    _transition(piece, Piece.SaleState.RESERVED, reason="checkout", ref=reference)
    return reservation


def _locked_reservation(reservation_id: int) -> tuple[Piece, PieceReservation]:
    # Every operation locks piece first, then reservation: a consistent lock order avoids deadlocks.
    piece_id = PieceReservation.objects.values_list("piece_id", flat=True).get(pk=reservation_id)
    piece = Piece.objects.select_for_update().get(pk=piece_id)
    reservation = PieceReservation.objects.select_for_update().get(pk=reservation_id)
    return piece, reservation


@transaction.atomic
def release_reservation(reservation_id: int, *, reason: str) -> None:
    piece, reservation = _locked_reservation(reservation_id)
    if reservation.status != PieceReservation.Status.ACTIVE:
        return
    reservation.status = PieceReservation.Status.RELEASED
    reservation.save(update_fields=["status"])
    if (
        piece.sale_state == Piece.SaleState.RESERVED
        and not PieceReservation.objects.filter(piece=piece, status="active").exists()
    ):
        _transition(piece, Piece.SaleState.AVAILABLE, reason=reason, ref=reservation.reference)


@transaction.atomic
def convert_reservation(reservation_id: int, *, reason: str) -> None:
    piece, reservation = _locked_reservation(reservation_id)
    if reservation.status != PieceReservation.Status.ACTIVE:
        return
    # An elapsed deadline does not invalidate a still-active reservation: late payment wins
    # while this reservation still owns the piece. Released/reallocated pieces cannot be sold.
    if (
        piece.sale_state != Piece.SaleState.RESERVED
        or PieceReservation.objects.filter(piece=piece, status="active")
        .exclude(pk=reservation.pk)
        .exists()
    ):
        raise PieceNotAvailable(state=piece.sale_state)
    reservation.status = PieceReservation.Status.CONVERTED
    reservation.save(update_fields=["status"])
    _transition(piece, Piece.SaleState.SOLD, reason=reason, ref=reservation.reference)


@transaction.atomic
def set_preorder(piece: Piece, value: bool, actor: User | AnonymousUser | None) -> None:
    piece = Piece.objects.select_for_update().get(pk=piece.pk)
    target = Piece.SaleState.PREORDER if value else Piece.SaleState.AVAILABLE
    if piece.sale_state not in (Piece.SaleState.AVAILABLE, Piece.SaleState.PREORDER):
        raise PieceNotAvailable(state=piece.sale_state)
    if piece.sale_state != target:
        _transition(piece, target, reason="admin", actor=actor)


def release_expired_reservations() -> int:
    # One short transaction per reservation: a failure on one piece must not roll back
    # the others, and locks are held only while that piece is being released.
    ids = list(
        PieceReservation.objects.filter(status="active", expires_at__lte=timezone.now())
        .order_by("piece_id")
        .values_list("pk", flat=True)
    )
    count = 0
    for reservation_id in ids:
        with transaction.atomic():
            _, reservation = _locked_reservation(reservation_id)
            if reservation.status == "active" and reservation.expires_at <= timezone.now():
                release_reservation(reservation_id, reason="reservation_expired")
                count += 1
    return count
