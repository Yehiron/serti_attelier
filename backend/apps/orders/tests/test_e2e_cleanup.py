from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework.test import APIClient

from apps.catalog.models import Piece
from apps.orders.models import Order
from apps.orders.tests.test_checkout import add, submit

pytestmark = pytest.mark.django_db


def test_cleanup_preserves_real_and_mixed_orders(piece, payload, settings):
    settings.DEBUG = True
    e2e = Piece.objects.create(
        sku="E2E-ONLY", name_es="E2E", slug_es="e2e-only", price_cents=100, status="published"
    )
    mixed_piece = Piece.objects.create(
        sku="E2E-MIXED", name_es="Mixed", slug_es="e2e-mixed", price_cents=100, status="published"
    )
    real_mixed = Piece.objects.create(
        sku="REAL-MIXED", name_es="Real", slug_es="real-mixed", price_cents=100, status="published"
    )
    for pieces in ([e2e], [piece], [mixed_piece, real_mixed]):
        client = APIClient()
        for item in pieces:
            assert add(client, item).status_code == 201
        assert submit(client, payload).status_code == 201
    ids = list(Order.objects.order_by("pk").values_list("pk", flat=True))
    output = StringIO()
    call_command("e2e_cleanup", dry_run=True, stdout=output)
    assert Order.objects.count() == 3 and Piece.objects.filter(pk=e2e.pk).exists()
    call_command("e2e_cleanup", stdout=output)
    assert not Order.objects.filter(pk=ids[0]).exists()
    assert set(Order.objects.values_list("pk", flat=True)) == set(ids[1:])
    assert not Piece.objects.filter(pk=e2e.pk).exists()
    assert Piece.objects.filter(pk__in=[piece.pk, mixed_piece.pk, real_mixed.pk]).count() == 3
    assert "Pedidos mixtos conservados" in output.getvalue()


def test_cleanup_requires_debug(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("e2e_cleanup")
