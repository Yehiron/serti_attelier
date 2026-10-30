from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.roles import CONTENIDO, OPERACIONES
from apps.accounts.services import sync_roles
from apps.catalog.models import Material, Piece, Stone
from apps.core.formatting import BOGOTA
from apps.core.models import Municipality
from apps.orders.models import Order, OrderItem

pytestmark = pytest.mark.django_db


@pytest.fixture
def certified(piece: Piece, payload: dict[str, Any]) -> Order:
    piece.stones.add(Stone.objects.create(name_es="Esmeralda", name_en="Emerald", slug_es="e"))
    piece.materials.add(Material.objects.create(name_es="Oro 18k", name_en="18k gold", slug_es="o"))
    order = Order.objects.create(
        number="SRT-CERT",
        idempotency_key=uuid4(),
        request_hash="x",
        customer_name="Ana Gómez",
        customer_email="ana@example.com",
        customer_phone="+573001234567",
        email_hash="x",
        shipping_address_line="Calle 123",
        shipping_municipality=Municipality.objects.get(pk="05001"),
        subtotal_cents=123456,
        total_cents=123456,
        payment_channel="wompi",
        payment_status="approved",
        paid_at=datetime(2026, 10, 25, 15, 0, tzinfo=BOGOTA),
        wants_certificate=True,
        terms_version=1,
        privacy_version=1,
        privacy_consent_at=timezone.now(),
    )
    OrderItem.objects.create(
        order=order,
        piece=piece,
        sku=piece.sku,
        piece_number="N.º 07",
        name_es="Anillo Esmeralda",
        name_en="Emerald Ring",
        unit_price_cents=123456,
    )
    return order


def browser_for(role: str) -> Client:
    sync_roles()
    user = User.objects.create_user(username=role, email=f"{role}@example.com", is_staff=True)
    user.groups.add(*user.groups.model.objects.filter(name=role))
    browser = Client()
    browser.force_login(user)
    return browser


def test_certificate_uses_floral_monogram_and_order_data(certified: Order) -> None:
    browser = browser_for(OPERACIONES)
    change = browser.get(reverse("admin:orders_order_change", args=[certified.pk]))
    url = reverse("admin:orders-certificate", args=[certified.pk])
    assert url in change.content.decode()
    page = browser.get(url).content.decode()
    assert "orders/floral-wine" in page
    for text in (
        "Certificado <em>de autenticidad</em>",
        "Anillo Esmeralda",
        "N.º 07",
        "Esmeralda",
        "Oro 18k",
        "Ana Gómez",
        "25 de octubre de 2026",
        "SRT-CERT-P5-A",
    ):
        assert text in page


def test_certificate_in_the_order_language(certified: Order) -> None:
    certified.locale = "en"
    certified.save()
    page = browser_for(OPERACIONES).get(reverse("admin:orders-certificate", args=[certified.pk]))
    content = page.content.decode()
    assert 'lang="en"' in content
    assert "Emerald Ring" in content and "18k gold" in content and "October 25, 2026" in content


@pytest.mark.parametrize("change", [{"wants_certificate": False}, {"payment_status": "pending"}])
def test_certificate_only_when_requested_and_paid(certified: Order, change: dict[str, Any]) -> None:
    Order.objects.filter(pk=certified.pk).update(**change)
    browser = browser_for(OPERACIONES)
    response = browser.get(reverse("admin:orders-certificate", args=[certified.pk]))
    assert response.status_code == 302
    assert response.headers["Location"] == reverse("admin:orders_order_change", args=[certified.pk])


def test_certificate_requires_order_permission(certified: Order) -> None:
    url = reverse("admin:orders-certificate", args=[certified.pk])
    assert browser_for(CONTENIDO).get(url).status_code == 403
    assert Client().get(url).status_code == 302
