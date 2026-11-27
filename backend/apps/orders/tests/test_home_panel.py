from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.core.cache import cache
from django.test import RequestFactory
from django.utils import timezone

from apps.catalog.models import PieceImage, Stone
from apps.inquiries.models import ContactInquiry
from apps.orders.metrics import dashboard_callback, home_greeting
from apps.orders.tests.test_operations import operator, order  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("hour", "expected"), [(8, "Buenos días"), (13, "Buenas tardes"), (20, "Buenas noches")]
)
def test_greeting(hour, expected):
    greeting, date = home_greeting(datetime(2026, 11, 26, hour, tzinfo=ZoneInfo("America/Bogota")))
    assert greeting == expected
    assert date == "Jueves 26 de noviembre"


def test_home_real_data(operator, order, piece, django_assert_max_num_queries):  # noqa: F811
    cache.clear()
    order.payment_status = "approved"
    order.fulfillment_status = "unfulfilled"
    order.paid_at = timezone.now()
    order.save()
    piece.status = "published"
    piece.sale_state = "available"
    piece.save()
    PieceImage.objects.create(piece=piece, original="one.webp", alt_es="Foto")
    Stone.objects.create(name_es="Esmeralda", description_es="texto de prueba")
    ContactInquiry.objects.create(
        name="Ana",
        email="ana@example.com",
        topic="piece",
        message="Una consulta sobre esta pieza",
        preferred_channel="email",
        privacy_version=1,
        locale="es",
    )
    request = RequestFactory().get("/")
    request.user = operator
    # The bound includes permission checks and all cold-cache aggregates.
    with django_assert_max_num_queries(35):
        context = dashboard_callback(request, {})
    assert context["home"]["today"]["count"] == 1
    assert context["home"]["pieces"]["count"] >= 1
    titles = " ".join(item["title"] for item in context["home"]["todos"])
    assert "Responder a Ana" in titles
    assert "menos de 2 fotos" in titles
    assert "texto de prueba" in titles
    assert "Por preparar" in titles


def test_no_sales_permission_and_empty_todos(db):
    from apps.accounts.models import User
    from apps.accounts.roles import CONTENIDO
    from apps.accounts.services import sync_roles

    sync_roles()
    user = User.objects.create_user(username="contenido-home", is_staff=True)
    user.groups.add(*user.groups.model.objects.filter(name=CONTENIDO))
    request = RequestFactory().get("/")
    request.user = user
    context = dashboard_callback(request, {})
    assert "shop_metrics" not in context
    assert "today" not in context["home"]
    assert context["home"]["todos"] == []
