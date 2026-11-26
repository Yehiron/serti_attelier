"""Deleting a sold piece must leave its paid order, payments and history intact."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.test import RequestFactory, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.roles import PROPIETARIO
from apps.catalog.models import Piece
from apps.catalog.services import hard_delete_blockers, hard_delete_piece
from apps.core.tests.test_dashboard_client import staff
from apps.inventory.models import PieceReservation, PieceStatusChange
from apps.orders.models import Order, OrderItem
from apps.payments.services import confirm_manual_payment
from apps.payments.tests.conftest import client, order, payload, piece, reset_cache  # noqa: F401
from apps.payments.tests.test_payments import manual_order, operator, proof  # noqa: F401

pytestmark = pytest.mark.django_db


def _pay(order: Order, operator: User, tmp_path: Any, capture: Any) -> None:  # noqa: F811
    manual_order(order)
    request = RequestFactory().post("/")
    request.user = operator
    with (
        override_settings(PRIVATE_MEDIA_ROOT=tmp_path),
        patch("apps.orders.events.order_paid"),
        capture(execute=True),
    ):
        confirm_manual_payment(
            order, actor=operator, reference="transfer", proof=proof(), request=request
        )


def test_pending_order_blocks_hard_delete(order: Order) -> None:  # noqa: F811
    _, actor = staff(PROPIETARIO)
    piece_obj = order.items.get().piece
    assert piece_obj is not None
    assert hard_delete_blockers(piece_obj)
    with pytest.raises(ValidationError):
        hard_delete_piece(piece_obj, actor=actor)
    assert Piece.objects.filter(pk=piece_obj.pk).exists()


def test_deleting_sold_piece_keeps_paid_order_intact(
    order: Order,  # noqa: F811
    operator: User,  # noqa: F811
    client: APIClient,  # noqa: F811
    tmp_path: Any,
    django_capture_on_commit_callbacks: Any,
) -> None:
    _pay(order, operator, tmp_path, django_capture_on_commit_callbacks)
    order.refresh_from_db()
    assert order.payment_status == "approved"
    item = order.items.get()
    piece_obj = item.piece
    assert piece_obj is not None and piece_obj.sale_state == "sold"
    before = (item.sku, item.name_es, item.unit_price_cents, order.total_cents)
    reservations = list(
        PieceReservation.objects.filter(piece=piece_obj).values_list("pk", flat=True)
    )
    changes = list(PieceStatusChange.objects.filter(piece=piece_obj).values_list("pk", flat=True))
    assert reservations and changes

    browser, actor = staff(PROPIETARIO)
    assert hard_delete_blockers(piece_obj) == []
    hard_delete_piece(piece_obj, actor=actor)

    assert not Piece.objects.filter(pk=piece_obj.pk).exists()
    order.refresh_from_db()
    item = OrderItem.objects.get(pk=item.pk)
    assert item.piece_id is None
    assert (item.sku, item.name_es, item.unit_price_cents, order.total_cents) == before
    assert order.payment_status == "approved"
    for row in PieceReservation.objects.filter(pk__in=reservations):
        assert row.piece_id is None and row.piece_sku == before[0]
    for change in PieceStatusChange.objects.filter(pk__in=changes):
        assert change.piece_id is None and change.piece_sku == before[0]

    # Every screen that shows the order still works.
    assert browser.get(reverse("admin:orders_order_change", args=[order.pk])).status_code in (
        200,
        302,
    )
    assert browser.get(reverse("admin:orders-card", args=[order.pk])).status_code == 200
    assert browser.get(reverse("admin:orders_order_changelist")).status_code == 200
    public = client.get(f"/api/v1/orders/{order.public_token}?locale=es")
    assert public.status_code == 200
    assert before[1] in public.content.decode()


def test_order_photo_survives_piece_deletion(
    order: Order,  # noqa: F811
    operator: User,  # noqa: F811
    tmp_path: Any,
    django_capture_on_commit_callbacks: Any,
) -> None:
    from io import BytesIO

    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage
    from PIL import Image

    from apps.catalog.models import PieceImage

    with override_settings(MEDIA_ROOT=tmp_path / "media"):
        _pay(order, operator, tmp_path, django_capture_on_commit_callbacks)
        item = order.items.get()
        piece_obj = item.piece
        assert piece_obj is not None
        buffer = BytesIO()
        Image.new("RGB", (40, 40), "#651c32").save(buffer, format="PNG")
        photo = PieceImage(piece=piece_obj, original=ContentFile(buffer.getvalue(), name="p.png"))
        photo.original.save("p.png", ContentFile(buffer.getvalue()), save=False)
        photo.save()
        old = photo.original.name
        assert old is not None
        assert default_storage.exists(old)
        # Test setup only: point the snapshot at the piece photo (OrderItem is immutable).
        from django.db.models import QuerySet

        QuerySet(model=OrderItem).filter(pk=item.pk).update(image_path=old)

        _, actor = staff(PROPIETARIO)
        with django_capture_on_commit_callbacks(execute=True):
            hard_delete_piece(piece_obj, actor=actor)

        item = OrderItem.objects.get(pk=item.pk)
        assert item.image_path and item.image_path != old
        assert item.image_path.startswith("orders/snapshots/")
        assert default_storage.exists(item.image_path)
