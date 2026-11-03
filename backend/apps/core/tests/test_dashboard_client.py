from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from django.contrib import admin
from django.contrib.auth.models import Group
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.accounts.roles import CONTENIDO, OPERACIONES, PROPIETARIO
from apps.accounts.services import sync_roles
from apps.catalog.forms import PesosField, PieceForm
from apps.catalog.models import Piece, PieceImage
from apps.cms.models import HeroSlide, HomeSection
from apps.core.dashboard import TECHNICAL_MODELS
from apps.core.models import Department, Municipality
from apps.orders.models import Order, OrderItem
from apps.promotions.admin import CouponForm

pytestmark = pytest.mark.django_db


def staff(role: str) -> tuple[Client, User]:
    sync_roles()
    user = User.objects.create_user(
        username=role, email=f"{role}@example.com", is_staff=True, is_superuser=role == "developer"
    )
    if role != "developer":
        user.groups.add(Group.objects.get(name=role))
    device = TOTPDevice.objects.create(user=user, confirmed=True)
    browser = Client()
    browser.force_login(user)
    session = browser.session
    session[DEVICE_ID_SESSION_KEY] = device.persistent_id
    session.save()
    return browser, user


@pytest.mark.parametrize(
    ("role", "areas"),
    [
        (PROPIETARIO, {"Pedidos", "Catálogo", "Página web", "Promociones", "Ajustes"}),
        (OPERACIONES, {"Pedidos", "Catálogo", "Página web", "Promociones"}),
        (CONTENIDO, {"Catálogo", "Página web"}),
        (
            "developer",
            {
                "Pedidos",
                "Catálogo",
                "Página web",
                "Promociones",
                "Ajustes",
                "Herramientas técnicas",
            },
        ),
    ],
)
def test_navigation_and_index(role: str, areas: set[str]) -> None:
    browser, _ = staff(role)
    response = browser.get(reverse("admin:index"))
    assert response.status_code == 200
    navigation = response.context["sidebar_navigation"]
    visible = {
        str(group["title"])
        for group in navigation
        if group.get("title") and any(i.get("has_permission") for i in group["items"])
    }
    assert visible == areas
    for app in response.context["app_list"]:
        for model in app["models"]:
            label = f"{app['app_label']}.{model['object_name'].lower()}"
            if role != "developer":
                assert label not in TECHNICAL_MODELS
    html = response.content.decode()
    if role != "developer":
        assert "Herramientas técnicas" not in html
    if role == CONTENIDO:
        assert "Agregar pieza" in html and "Publicar inicio" in html
        assert "Pedidos pendientes de pago" not in html


@pytest.mark.parametrize("role", [PROPIETARIO, OPERACIONES, CONTENIDO])
@pytest.mark.parametrize("model", sorted(TECHNICAL_MODELS))
def test_technical_screens_denied(role: str, model: str) -> None:
    browser, _ = staff(role)
    app, name = model.split(".")
    assert browser.get(reverse(f"admin:{app}_{name}_changelist")).status_code == 403


def test_customer_order_sheet() -> None:
    browser, _ = staff(PROPIETARIO)
    department = Department.objects.get_or_create(code="05", defaults={"name": "Antioquia"})[0]
    municipality = Municipality.objects.get_or_create(
        code="05001", defaults={"name": "Medellín", "department": department, "kind": "Municipio"}
    )[0]
    piece = Piece.objects.create(
        sku="TEST-CLIENT", name_es="Anillo", slug_es="anillo", price_cents=125000000
    )
    order = Order.objects.create(
        number="SRT-CLIENT",
        idempotency_key=uuid4(),
        request_hash="private-request-hash",
        email_hash="private-email-hash",
        customer_name="Ana Cliente",
        customer_email="ana@example.com",
        customer_phone="3001234567",
        shipping_address_line="Calle 123",
        shipping_municipality=municipality,
        subtotal_cents=125000000,
        total_cents=125000000,
        payment_channel="manual",
        terms_version=1,
        privacy_version=1,
        privacy_consent_at=timezone.now(),
    )
    OrderItem.objects.create(
        order=order,
        piece=piece,
        sku=piece.sku,
        name_es="Anillo comprado",
        unit_price_cents=125000000,
    )
    response = browser.get(reverse("admin:orders_order_change", args=[order.pk]))
    assert response.status_code == 200
    html = response.content.decode()
    for value in (
        "Ana Cliente",
        "Calle 123",
        municipality.department.name,
        municipality.name,
        "Anillo comprado",
        "$1.250.000",
        "https://wa.me/573001234567",
        "mailto:ana@example.com",
    ):
        assert value in html
    for value in (
        order.public_token,
        str(order.idempotency_key),
        order.request_hash,
        order.email_hash,
    ):
        assert value not in html
    for name in ("payment_attempts", "notification_deliveries", "public_token", "idempotency_key"):
        assert name not in html


def test_image_forms_and_sorting() -> None:
    browser, user = staff(PROPIETARIO)
    section = HomeSection.objects.create(
        kind="statement", title_es="Inicio", renditions={"secret-rendition": "internal.webp"}
    )
    html = browser.get(reverse("admin:cms_homesection_change", args=[section.pk])).content.decode()
    assert "secret-rendition" not in html and "internal.webp" not in html
    assert "Vista previa" in html
    piece = Piece.objects.create(sku="IMAGE", name_es="Anillo", slug_es="image", price_cents=100000)
    PieceImage.objects.create(
        piece=piece,
        original="tests/photo.webp",
        alt_es="Anillo",
        processing_status="failed",
        error="Traceback /srv/private/decoder",
        renditions={"internal-json-marker": "private-image-data"},
    )
    piece_html = browser.get(
        reverse("admin:catalog_piece_change", args=[piece.pk])
    ).content.decode()
    assert "internal-json-marker" not in piece_html and "private-image-data" not in piece_html
    assert "Traceback /srv/private/decoder" not in piece_html
    assert "Error: vuelve a subir la imagen" in piece_html
    hero = HomeSection.objects.create(kind="hero", title_es="Portada")
    HeroSlide.objects.create(
        section=hero,
        image="tests/slide.webp",
        alt_es="Portada",
        alt_en="Home",
        renditions={"slide-internal-marker": "private-slide-data"},
    )
    hero_html = browser.get(
        reverse("admin:cms_homesection_change", args=[hero.pk])
    ).content.decode()
    assert "slide-internal-marker" not in hero_html and "private-slide-data" not in hero_html
    assert "Lista" in hero_html
    request = RequestFactory().get("/")
    request.user = user
    model_admin: Any = admin.site._registry[HomeSection]
    assert model_admin.ordering_field == "position"
    assert model_admin.hide_ordering_field


@pytest.mark.parametrize("cents", [125000000, 123456, 0])
def test_pesos_round_trip(cents: int) -> None:
    field = PesosField(min_value=0)
    assert field.clean(str(field.prepare_value(cents))) == cents
    assert PieceForm.base_fields["price_cents"].clean("1250000") == 125000000
    assert CouponForm.base_fields["min_subtotal_cents"].clean("10000") == 1000000


def test_owner_resets_teammate_device() -> None:
    browser, _ = staff(PROPIETARIO)
    teammate = User.objects.create_user(
        username="teammate", email="team@example.com", is_staff=True
    )
    device = TOTPDevice.objects.create(user=teammate, confirmed=True)
    url = reverse("admin:accounts_user_change", args=[teammate.pk])
    page = browser.get(url)
    formset = page.context["inline_admin_formsets"][0].formset
    prefix = formset.prefix
    data: dict[str, Any] = {
        "username": teammate.username,
        "email": teammate.email,
        "is_active": "on",
        "role": OPERACIONES,
        "date_joined_0": "2026-10-23",
        "date_joined_1": "12:00:00",
        f"{prefix}-0-id": device.pk,
        f"{prefix}-0-DELETE": "on",
    }
    for key, value in formset.management_form.initial.items():
        data[f"{prefix}-{key}"] = value
    assert browser.post(url, data).status_code == 302
    assert not TOTPDevice.objects.filter(pk=device.pk).exists()


def test_price_form_persists_pesos_via_service() -> None:
    from apps.catalog.services import save_piece

    _, owner = staff(PROPIETARIO)
    request = RequestFactory().get("/")
    request.user = owner
    model_admin: Any = admin.site._registry[Piece]
    form = model_admin.get_form(request)(
        data={
            "sku": "PESOS",
            "name_es": "Anillo",
            "name_en": "Ring",
            "slug_es": "pesos",
            "slug_en": "pesos",
            "price_cents": "1250000.25",
            "position": "0",
        }
    )
    assert form.is_valid(), form.errors
    piece = save_piece(form.save(commit=False), actor=owner)
    piece.refresh_from_db()
    assert piece.price_cents == 125000025
    assert PieceForm(instance=piece)["price_cents"].value() == 1250000.25


def test_content_sees_readonly_pesos() -> None:
    browser, _ = staff(CONTENIDO)
    piece = Piece.objects.create(
        sku="READONLY", name_es="Anillo", slug_es="readonly", price_cents=125000000
    )
    response = browser.get(reverse("admin:catalog_piece_change", args=[piece.pk]))
    assert response.status_code == 200
    html = response.content.decode()
    assert "$1.250.000" in html and "centavos" not in html
    assert 'name="price_cents"' not in html
    assert browser.get(reverse("admin:catalog_piece_add")).status_code == 200


@pytest.mark.parametrize("model", ["category", "homesection"])
def test_sorting_uses_existing_save_service(model: str) -> None:
    from unittest.mock import patch

    from apps.catalog import services as catalog_services
    from apps.catalog.models import Category
    from apps.cms import services as cms_services

    browser, _ = staff(PROPIETARIO)
    obj: Any
    service: Any
    if model == "category":
        obj = Category.objects.create(name_es="Anillos", slug_es="sort-test")
        url = reverse("admin:catalog_category_changelist")
        target = "apps.catalog.services.save_taxonomy"
        service = catalog_services.save_taxonomy
    else:
        obj = HomeSection.objects.create(kind="statement", title_es="Historia")
        url = reverse("admin:cms_homesection_changelist")
        target = "apps.cms.services.save_section"
        service = cms_services.save_section
    page = browser.get(url)
    formset = page.context["cl"].formset
    data: dict[str, Any] = {"_save": "Guardar"}
    for key, value in formset.management_form.initial.items():
        data[f"{formset.prefix}-{key}"] = value
    for form in formset.forms:
        data[f"{form.prefix}-id"] = form.instance.pk
        data[f"{form.prefix}-position"] = (
            17 if form.instance.pk == obj.pk else form.instance.position
        )
    with patch(target, wraps=service) as saved:
        response = browser.post(url, data)
        assert response.status_code == 302
        saved.assert_called_once()
    obj.refresh_from_db()
    assert obj.position == 17


def test_branding_and_spanish_device_label() -> None:
    browser, _ = staff("developer")
    html = browser.get(reverse("admin:index")).content.decode()
    for asset in ("wordmark-wine.webp", "wordmark-gold.webp", "favicon.svg"):
        assert asset in html
    assert "TOTP devices" not in html
    assert "Dispositivos de verificación" in html
    for model in (
        "axes_accessattempt",
        "payments_paymentevent",
        "notifications_notificationdelivery",
        "otp_totp_totpdevice",
    ):
        response = browser.get(reverse(f"admin:{model}_changelist"))
        assert response.status_code == 200
        assert "TOTP devices" not in response.content.decode()
