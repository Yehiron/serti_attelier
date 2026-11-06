import json
from datetime import timedelta

import pytest
from django.contrib import admin
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.roles import CONTENIDO, OPERACIONES, PROPIETARIO
from apps.core.tests.test_dashboard_client import staff
from apps.orders.models import Order
from apps.orders.tests.test_card import order as order_fixture

order = order_fixture
pytestmark = pytest.mark.django_db


def test_anonymous_json_is_403():
    response = Client().get(reverse("admin:orders-center-json"))
    assert response.status_code == 403
    assert "amount" not in response.content.decode()


@pytest.mark.parametrize(
    "role,allowed", [(PROPIETARIO, True), (OPERACIONES, True), (CONTENIDO, False)]
)
def test_json_permissions(order, role, allowed):
    browser, _ = staff(role)
    response = browser.get(reverse("admin:orders-center-json"))
    assert response.status_code == (200 if allowed else 403)
    if not allowed:
        assert "amount" not in response.content.decode()


def test_json_budget_filters_and_period(order, django_assert_max_num_queries):
    _, actor = staff(PROPIETARIO)
    # Fresh user: permission queries are included, session/OTP middleware are not.
    actor = User.objects.get(pk=actor.pk)
    order.payment_status = "approved"
    order.paid_at = timezone.now() - timedelta(days=2)
    order.save()
    request = RequestFactory().get("/", {"period": "seven_days", "q": order.number})
    request.user = actor
    model_admin = admin.site._registry[Order]
    with django_assert_max_num_queries(6):
        response = model_admin.center_json(request)
    data = json.loads(response.content)
    assert data["metrics"][0]["count"] == 1
    assert data["tabs"][0]["count"] == data["tabs"][1]["count"] == 1
    request.GET = request.GET.copy()
    request.GET["period"] = "today"
    request.GET["payment_status__exact"] = "pending"
    data = json.loads(model_admin.center_json(request).content)
    assert data["metrics"][0]["count"] == 0
    assert data["tabs"][0]["count"] == data["tabs"][1]["count"] == 0


def test_compact_markup(order):
    browser, _ = staff(PROPIETARIO)
    response = browser.get(reverse("admin:orders_order_changelist"))
    html = response.content.decode()
    for marker in (
        "field-number",
        "field-client_name",
        "oc-client-name",
        "oc-client-phone",
        "oc-select-order",
        "oc-date-mobile",
        "field-total_cop",
        "field-view_order",
        "data-center-url",
        "data-metric-value",
        "data-tab-count",
        'aria-live="polite"',
    ):
        assert marker in html
    assert "oc-date-desktop" in html


def test_change_only_user_receives_no_amounts(order):
    from django.contrib.auth.models import Permission

    actor = User.objects.create_user(username="change-only", is_staff=True)
    actor.user_permissions.add(Permission.objects.get(codename="change_order"))
    request = RequestFactory().get("/")
    request.user = actor
    response = admin.site._registry[Order].center_json(request)
    assert response.status_code == 200
    assert "amount" not in response.content.decode()
