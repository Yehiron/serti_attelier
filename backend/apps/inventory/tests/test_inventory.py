from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from django.db import close_old_connections, connection, transaction
from django.utils import timezone

from apps.catalog.models import Piece
from apps.inventory.models import PieceReservation, PieceStatusChange
from apps.inventory.services import (
    PieceNotAvailable,
    convert_reservation,
    release_expired_reservations,
    release_reservation,
    reserve_piece,
    set_preorder,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def piece() -> Piece:
    return Piece.objects.create(sku="INV-1", name_es="Pieza", slug_es="pieza", price_cents=10000)


def reserve(piece: Piece, *, expired: bool = False) -> PieceReservation:
    return reserve_piece(
        piece.pk,
        kind="online",
        reference="order",
        expires_at=timezone.now() + timedelta(minutes=-1 if expired else 30),
    )


def test_release_expire_and_logs(piece: Piece) -> None:
    reservation = reserve(piece)
    piece.refresh_from_db()
    assert piece.sale_state == "reserved"
    with pytest.raises(PieceNotAvailable) as exc:
        reserve(piece)
    assert exc.value.state == "reserved"
    release_reservation(reservation.pk, reason="released")
    release_reservation(reservation.pk, reason="released")
    piece.refresh_from_db()
    assert piece.sale_state == "available"
    reserve(piece, expired=True)
    assert release_expired_reservations() == 1
    assert release_expired_reservations() == 0
    piece.refresh_from_db()
    assert piece.sale_state == "available"
    assert list(PieceStatusChange.objects.order_by("pk").values_list("reason", flat=True)) == [
        "checkout",
        "released",
        "checkout",
        "reservation_expired",
    ]
    change = PieceStatusChange.objects.first()
    assert change is not None
    with pytest.raises(ValueError):
        change.delete()
    with pytest.raises(ValueError):
        change.save()
    with pytest.raises(ValueError):
        PieceStatusChange.objects.update(ref="changed")


@pytest.mark.parametrize("expired", [False, True])
def test_convert_and_terminal(piece: Piece, expired: bool) -> None:
    reservation = reserve(piece, expired=expired)
    convert_reservation(reservation.pk, reason="payment_approved")
    convert_reservation(reservation.pk, reason="payment_approved")
    release_reservation(reservation.pk, reason="released")
    piece.refresh_from_db()
    reservation.refresh_from_db()
    assert piece.sale_state == "sold"
    assert piece.sold_at is not None
    assert reservation.status == "converted"
    with pytest.raises(PieceNotAvailable):
        reserve(piece)
    with pytest.raises(PieceNotAvailable):
        set_preorder(piece, False, None)
    assert PieceStatusChange.objects.count() == 2


def test_preorder_and_released_reservation_cannot_convert(piece: Piece) -> None:
    set_preorder(piece, True, None)
    with pytest.raises(PieceNotAvailable) as exc:
        reserve(piece)
    assert exc.value.state == "preorder"
    set_preorder(piece, False, None)
    old = reserve(piece)
    release_reservation(old.pk, reason="released")
    new = reserve(piece)
    convert_reservation(old.pk, reason="payment_approved")
    piece.refresh_from_db()
    assert piece.sale_state == "reserved"
    assert PieceReservation.objects.get(pk=new.pk).status == "active"


def test_one_active_constraint(piece: Piece) -> None:
    from django.db import IntegrityError

    reserve(piece)
    with pytest.raises(IntegrityError), transaction.atomic():
        PieceReservation.objects.create(piece=piece, kind="manual", expires_at=timezone.now())


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_concurrent_reservations_exactly_one_wins(piece: Piece) -> None:
    barrier = Barrier(2)
    piece_id = piece.pk

    def attempt(reference: str) -> str:
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            reserve_piece(
                piece_id,
                kind="online",
                reference=reference,
                expires_at=timezone.now() + timedelta(minutes=30),
            )
            return "reserved"
        except PieceNotAvailable:
            return "unavailable"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ["first", "second"]))
    assert sorted(results) == ["reserved", "unavailable"]
    assert PieceReservation.objects.filter(status="active", piece_id=piece_id).count() == 1
    assert PieceStatusChange.objects.filter(piece_id=piece_id).count() == 1
