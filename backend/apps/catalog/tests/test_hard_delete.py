import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.accounts.roles import CONTENIDO, PROPIETARIO
from apps.audit.models import AuditLog
from apps.catalog.models import Piece
from apps.catalog.services import hard_delete_piece, hard_delete_pieces
from apps.cms.models import Redirect
from apps.core.tests.test_dashboard_client import staff
from apps.inventory.models import PieceReservation

pytestmark = pytest.mark.django_db


def test_published_piece_deleted_and_redirected(make_piece):
    _, actor = staff(PROPIETARIO)
    piece = make_piece()
    pk = piece.pk
    hard_delete_piece(piece, actor=actor)
    assert not Piece.objects.filter(pk=pk).exists()
    assert Redirect.objects.filter(
        from_path="/es/piezas/pieza-1", to_path="/es/joyeria/anillos", status_code=301
    ).exists()
    assert AuditLog.objects.filter(action="catalog.piece_deleted", actor=actor).exists()


def test_active_reservation_blocks_batch(make_piece):
    _, actor = staff(PROPIETARIO)
    first = make_piece(published=False)
    second = make_piece(published=False)
    PieceReservation.objects.create(
        piece=second,
        piece_sku=second.sku,
        piece_name_es=second.name_es,
        kind="manual",
        expires_at=timezone.now(),
    )
    with pytest.raises(ValidationError):
        hard_delete_pieces(Piece.objects.filter(pk__in=[first.pk, second.pk]), actor=actor)
    assert Piece.objects.filter(pk__in=[first.pk, second.pk]).count() == 2


def test_content_role_cannot_delete(make_piece):
    _, actor = staff(CONTENIDO)
    piece = make_piece(published=False)
    with pytest.raises(PermissionDenied):
        hard_delete_piece(piece, actor=actor)
    assert Piece.objects.filter(pk=piece.pk).exists()


def test_delete_screen_requires_exact_sku(make_piece):
    from django.urls import reverse

    browser, _ = staff(PROPIETARIO)
    piece = make_piece()
    url = reverse("admin:catalog_piece_delete", args=[piece.pk])
    response = browser.get(url)
    assert response.status_code == 200
    assert all(label in response.content.decode() for label in ("Archivar", "Ocultar", "Eliminar"))
    browser.post(url, {"action": "delete", "sku": "incorrecto"})
    assert Piece.objects.filter(pk=piece.pk).exists()
    browser.post(url, {"action": "delete", "sku": piece.sku})
    assert not Piece.objects.filter(pk=piece.pk).exists()


def test_delete_screen_rejects_content_role(make_piece):
    from django.urls import reverse

    browser, _ = staff(CONTENIDO)
    piece = make_piece()
    assert browser.get(reverse("admin:catalog_piece_delete", args=[piece.pk])).status_code == 403
