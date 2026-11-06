from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.admin.sites import site
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.roles import CONTENIDO, OPERACIONES, PROPIETARIO
from apps.accounts.services import sync_roles
from apps.audit.models import AuditLog
from apps.catalog.models import (
    Category,
    Collection,
    CollectionPiece,
    Material,
    Piece,
    PieceImage,
    Stone,
)
from apps.catalog.services import duplicate_piece
from apps.core.formatting import BOGOTA, format_cop
from apps.core.models import Municipality
from apps.notifications.models import NotificationDelivery
from apps.notifications.rendering import render_email
from apps.notifications.services import enqueue
from apps.orders.admin import OrderAdmin
from apps.orders.exceptions import CheckoutError
from apps.orders.exports import COLUMNS, export_orders
from apps.orders.metrics import compute_metrics, dashboard_callback
from apps.orders.models import Order, OrderNote
from apps.orders.services import add_order_note, transition_status
from apps.promotions.models import Coupon, CouponRedemption

pytestmark = pytest.mark.django_db


@pytest.fixture
def order(payload: dict[str, Any]) -> Order:
    return Order.objects.create(
        number="SRT-OP",
        idempotency_key=uuid4(),
        request_hash="x",
        customer_name="Cliente",
        customer_email="client@example.com",
        customer_phone="+573001234567",
        email_hash="x",
        shipping_address_line="Calle 123",
        shipping_municipality=Municipality.objects.get(pk="05001"),
        subtotal_cents=100000,
        total_cents=100000,
        payment_channel="wompi",
        terms_version=1,
        privacy_version=1,
        privacy_consent_at=timezone.now(),
    )


@pytest.fixture
def operator() -> User:
    sync_roles()
    user = User.objects.create_user(username="operator", email="op@example.com", is_staff=True)
    user.groups.add(*user.groups.model.objects.filter(name=OPERACIONES))
    return user


def request_for(user: User) -> Any:
    request = RequestFactory().post("/")
    request.user = user
    return request


@pytest.mark.parametrize(
    "locale,heading",
    [
        ("es", "Tu pieza va en camino"),
        ("en", "Your piece is on its way"),
    ],
)
def test_shipping(
    order: Order,
    operator: User,
    locale: str,
    heading: str,
    piece: Piece,
    django_capture_on_commit_callbacks: Any,
) -> None:
    from .helpers import sell_item_to_order

    sell_item_to_order(order, piece)
    order.locale = locale
    order.payment_status = "approved"
    order.fulfillment_status = "preparing"
    order.save()
    request = request_for(operator)
    with pytest.raises(ValidationError):
        transition_status(order, "fulfillment_status", "shipped", request=request)
    with pytest.raises(ValidationError):
        transition_status(
            order,
            "fulfillment_status",
            "shipped",
            request=request,
            carrier="Carrier",
            tracking_url="http://tracking.example.com",
        )
    with (
        patch("apps.notifications.services.dispatch"),
        django_capture_on_commit_callbacks(execute=True),
    ):
        transition_status(
            order,
            "fulfillment_status",
            "shipped",
            request=request,
            note="Empacado",
            carrier="Carrier",
            tracking_number="ABC",
            tracking_url="https://tracking.example.com/ABC",
        )
    order.refresh_from_db()
    assert order.carrier == "Carrier" and order.shipped_at and not order.delivered_at
    assert order.status_changes.get().note == "Empacado\nCorreo al cliente encolado."
    delivery = NotificationDelivery.objects.get()
    content = render_email(delivery, order)
    for body in (content.text, content.html):
        assert heading in body and "Carrier" in body and "ABC" in body
        assert order.tracking_url in body and order.shipping_address_line in body
        assert "/pedido" in body or "/order" in body
    assert heading in content.subject
    assert enqueue(order, "order_shipped", event_key=f"status:{order.status_changes.get().pk}") == 0
    order.save()
    assert NotificationDelivery.objects.count() == 1
    with pytest.raises(CheckoutError):
        transition_status(order, "fulfillment_status", "shipped", request=request, carrier="Other")
    transition_status(order, "fulfillment_status", "delivered", request=request)
    order.refresh_from_db()
    assert order.delivered_at and order.delivered_at >= order.shipped_at
    assert AuditLog.objects.filter(action="orders.status_changed").count() == 2


def test_shipping_permission_optional_tracking(order: Order, piece: Piece, operator: User) -> None:
    from .helpers import sell_item_to_order

    sell_item_to_order(order, piece)
    with pytest.raises(PermissionDenied):
        transition_status(order, "fulfillment_status", "shipped", carrier="Carrier")
    Order.objects.filter(pk=order.pk).update(
        payment_status="approved", fulfillment_status="preparing"
    )
    transition_status(
        order, "fulfillment_status", "shipped", request=request_for(operator), carrier="Carrier"
    )
    order.refresh_from_db()
    assert order.shipped_at and order.tracking_number == "" and order.tracking_url == ""


def test_notes_append_only(order: Order, operator: User) -> None:
    request = request_for(operator)
    note = add_order_note(order, "  Empacar con cuidado  ", request=request)
    assert note.text == "Empacar con cuidado" and note.author == operator
    assert AuditLog.objects.filter(action="orders.note_added", object_id=str(note.pk)).exists()
    with pytest.raises(ValueError):
        note.save()
    with pytest.raises(ValueError):
        note.delete()
    with pytest.raises(ValueError):
        OrderNote.objects.update(text="changed")
    with pytest.raises(ValueError):
        OrderNote.objects.all().delete()
    with pytest.raises(ValidationError):
        add_order_note(order, "x" * 2001, request=request)
    with pytest.raises(ValidationError):
        add_order_note(order, "  ", request=request)


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_csv(order: Order, operator: User, prefix: str) -> None:
    order.customer_name = prefix + "formula"
    order.save()
    response = export_orders(Order.objects.all(), request=request_for(operator))
    content = response.content.decode()
    assert content.startswith("\ufeff")  # Excel needs the BOM to show accents
    rows = list(csv.reader(io.StringIO(content.lstrip("\ufeff")), delimiter=";"))
    assert rows[0] == list(COLUMNS)
    assert rows[1][2] == "'" + prefix + "formula"
    assert rows[1][4].startswith("'+")
    assert rows[1][8] == str(order.subtotal_cents // 100)  # whole pesos, not cents
    assert "Colombia" in rows[1][1]
    assert rows[1][5] == rows[1][5].title() or " de " in rows[1][5]  # DANE names readable
    assert AuditLog.objects.filter(action="orders.exported", object_id=str(order.pk)).exists()


def test_content_permissions(order: Order, piece: Piece) -> None:
    sync_roles()
    user = User.objects.create_user(username="content", email="content@example.com", is_staff=True)
    user.groups.add(user.groups.model.objects.get(name=CONTENIDO))
    request = request_for(user)
    assert "shop_metrics" not in dashboard_callback(request, {})
    with pytest.raises(PermissionDenied):
        export_orders(Order.objects.all(), request=request)
    with pytest.raises(PermissionDenied):
        add_order_note(order, "Hello", request=request)
    with pytest.raises(PermissionDenied):
        transition_status(order, "fulfillment_status", "preparing", request=request)
    with pytest.raises(PermissionDenied):
        duplicate_piece(piece, user)


def test_duplicate(piece: Piece, operator: User) -> None:
    category = Category.objects.create(name_es="Anillos", slug_es="anillos")
    stone = Stone.objects.create(name_es="Esmeralda", slug_es="esmeralda")
    material = Material.objects.create(name_es="Oro", slug_es="oro")
    collection = Collection.objects.create(name_es="Regalos", slug_es="regalos")
    piece.category = category
    piece.piece_number = "1/1"
    piece.sale_state = "sold"
    piece.sold_at = timezone.now()
    piece.attributes = {"weight_g": "2"}
    piece.save()
    piece.stones.add(stone)
    piece.materials.add(material)
    CollectionPiece.objects.create(piece=piece, collection=collection, position=3)
    PieceImage.objects.create(piece=piece, original="original.webp", alt_es="Test")
    copy = duplicate_piece(piece, operator)
    second = duplicate_piece(piece, operator)
    assert copy.sku != second.sku and copy.sku != piece.sku
    for locale in ("es", "en"):
        assert getattr(copy, f"slug_{locale}") != getattr(second, f"slug_{locale}")
        assert getattr(copy, f"name_{locale}").endswith(" (copia)")
    assert copy.status == "draft" and copy.sale_state == "available"
    assert not copy.piece_number and not copy.published_at and not copy.sold_at
    assert copy.attributes == piece.attributes and copy.category == category
    assert list(copy.stones.all()) == [stone] and list(copy.materials.all()) == [material]
    assert CollectionPiece.objects.get(piece=copy).position == 3
    assert not copy.images.exists() and not copy.related.exists()
    assert AuditLog.objects.filter(
        action="catalog.piece_duplicated", object_id=str(copy.pk)
    ).exists()


def test_approved_metrics_and_query_budget(order: Order, django_assert_num_queries: Any) -> None:
    now = datetime(2026, 10, 1, 0, 30, tzinfo=BOGOTA)
    for index, status in enumerate(("approved", "pending", "declined", "expired", "voided")):
        clone = Order.objects.get(pk=order.pk)
        clone.pk = None
        clone.number = f"MET-{index}"
        clone.idempotency_key = uuid4()
        clone.public_token = str(uuid4())
        clone.payment_status = status
        clone.paid_at = now - timedelta(minutes=10)
        clone.save()
    # UTC October 1, but still September in Bogota.
    Order.objects.filter(pk=order.pk).update(
        payment_status="approved", paid_at=now - timedelta(hours=1)
    )
    with django_assert_num_queries(10):
        metrics = compute_metrics(now)
    cards = {row["key"]: row for row in metrics["sales"]}
    assert cards["today"]["count"] == 1 and cards["month"]["count"] == 1
    assert cards["seven_days"]["count"] == 2 and cards["thirty_days"]["count"] == 2
    assert cards["today"]["total"] == format_cop(100000, "es").replace("$ ", "$")
    assert metrics["monthly"][-1]["count"] == 1
    assert metrics["monthly"][-2]["count"] == 1
    assert metrics["monthly"][-1]["width"] == 100


def test_discounts_health(order: Order, piece: Piece) -> None:
    now = timezone.now()
    order.payment_status = "approved"
    order.paid_at = now
    order.discount_cents = 1000
    order.total_cents -= 1000
    order.save()
    coupon = Coupon.objects.create(code="TEST", kind="fixed", value=1000)
    CouponRedemption.objects.create(coupon=coupon, order=order, email_hash="hash")
    PieceImage.objects.create(
        piece=piece, original="failed.webp", alt_es="Failed", processing_status="failed"
    )
    PieceImage.objects.create(
        piece=piece,
        original="failed2.webp",
        alt_es="Failed",
        position=1,
        processing_status="failed",
    )
    metrics = compute_metrics()
    assert metrics["discounts"]["count"] == 1 and metrics["discounts"]["total"] == 1000
    assert metrics["health"][0]["count"] == 1
    assert metrics["health"][-1]["count"] == 1
    assert metrics["health"][-2]["count"] == 1
    order.payment_status = "voided"
    order.save()
    assert compute_metrics(now)["discounts"]["count"] == 0


def test_dashboard_cache_and_roles(operator: User, django_assert_num_queries: Any) -> None:
    cache.clear()
    request = request_for(operator)
    dashboard_callback(request, {})
    # Warm the permission cache too; a cache hit performs no ORM work.
    with django_assert_num_queries(0):
        assert "shop_metrics" in dashboard_callback(request, {})
    for role in (PROPIETARIO, OPERACIONES):
        from apps.accounts.roles import ROLE_PERMISSIONS

        assert {
            "orders.add_ordernote",
            "orders.view_ordernote",
            "orders.export_orders",
            "orders.view_order",
        } <= ROLE_PERMISSIONS[role]


def test_admin_search_and_form(
    order: Order,
    piece: Piece,
    operator: User,
    client: Any,
) -> None:
    from apps.orders.models import OrderItem

    OrderItem.objects.create(
        order=order,
        piece=piece,
        sku="SNAPSHOT-SKU",
        name_es="Pieza",
        name_en="Piece",
        attributes={},
        unit_price_cents=100000,
        discount_cents=0,
    )
    model_admin = OrderAdmin(Order, site)
    found, duplicates = model_admin.get_search_results(
        request_for(operator), Order.objects.all(), "SNAPSHOT-SKU"
    )
    assert list(found) == [order] and duplicates
    browser = Client()
    browser.force_login(operator)
    index = browser.get(reverse("admin:index"))
    assert index.status_code == 200 and "shop_metrics" in index.context
    response = browser.post(
        reverse("admin:orders_order_changelist"),
        {
            "action": "fulfillment",
            "_selected_action": [order.pk],
        },
    )
    assert response.status_code == 200 and "form" in response.context
    response = browser.post(
        reverse("admin:orders_order_changelist"),
        {
            "action": "fulfillment",
            "_selected_action": [order.pk],
            "apply": "1",
            "target": "cancelled",
            "note": "Cancelación",
        },
    )
    assert response.status_code == 200
    assert "cancelled" not in dict(response.context["form"].fields["target"].choices)
    order.refresh_from_db()
    assert order.fulfillment_status == "unfulfilled"
    assert not order.status_changes.exists()
    change = browser.get(reverse("admin:orders_order_change", args=[order.pk]))
    assert change.status_code == 200


def test_notes_admin_append_only(order: Order, operator: User) -> None:
    browser = Client()
    browser.force_login(operator)
    url = reverse("admin:orders-card-note", args=[order.pk])
    assert browser.post(url, {"text": "Primera nota"}).status_code == 200
    assert (
        browser.post(url, {"text": "Segunda nota", "notes-0-text": "Tampered"}).status_code == 200
    )
    assert list(order.notes.values_list("text", flat=True)) == ["Primera nota", "Segunda nota"]
    assert AuditLog.objects.filter(action="orders.note_added").count() == 2


def test_health_links_match_filters(piece: Piece, operator: User) -> None:
    browser = Client()
    browser.force_login(operator)
    metrics = compute_metrics()
    for row in metrics["health"]:
        response = browser.get(row["url"])
        assert response.status_code == 200
        assert response.context["cl"].result_count == row["count"]


def test_normal_index_for_content() -> None:
    sync_roles()
    user = User.objects.create_user(username="editor", email="editor@example.com", is_staff=True)
    user.groups.add(user.groups.model.objects.get(name=CONTENIDO))
    browser = Client()
    browser.force_login(user)
    response = browser.get(reverse("admin:index"))
    assert response.status_code == 200
    assert "shop_metrics" not in response.context
    assert b"dashboard" in response.content


def test_shipping_rollback(
    order: Order, piece: Piece, operator: User, django_capture_on_commit_callbacks: Any
) -> None:
    from django.db import transaction

    from .helpers import sell_item_to_order

    sell_item_to_order(order, piece)

    Order.objects.filter(pk=order.pk).update(
        payment_status="approved", fulfillment_status="preparing"
    )
    with (
        django_capture_on_commit_callbacks(execute=True),
        pytest.raises(ValueError),
        transaction.atomic(),
    ):
        transition_status(
            order, "fulfillment_status", "shipped", request=request_for(operator), carrier="Carrier"
        )
        raise ValueError
    order.refresh_from_db()
    assert order.fulfillment_status == "preparing" and order.shipped_at is None
    assert not NotificationDelivery.objects.exists()


def test_duplicate_relations_texts_and_single_admin_redirect(piece: Piece, operator: User) -> None:
    other = Piece.objects.create(sku="OTHER", name_es="Otra", slug_es="otra", price_cents=100)
    piece.related.add(other)
    for field in (
        "short_description",
        "long_description",
        "story",
        "care",
        "seo_title",
        "seo_description",
    ):
        for locale in ("es", "en"):
            setattr(piece, f"{field}_{locale}", f"{field} {locale}")
    piece.save()
    browser = Client()
    browser.force_login(operator)
    response = browser.post(
        reverse("admin:catalog_piece_changelist"),
        {
            "action": "duplicate",
            "_selected_action": [piece.pk],
        },
    )
    copy = Piece.objects.exclude(pk__in=[piece.pk, other.pk]).get()
    assert response.status_code == 302
    assert response["Location"] == reverse("admin:catalog_piece_change", args=[copy.pk])
    assert not copy.related.exists()
    for field in (
        "short_description",
        "long_description",
        "story",
        "care",
        "seo_title",
        "seo_description",
    ):
        for locale in ("es", "en"):
            assert getattr(copy, f"{field}_{locale}") == getattr(piece, f"{field}_{locale}")


def test_shipped_delivery_sends_once(
    order: Order, piece: Piece, operator: User, django_capture_on_commit_callbacks: Any
) -> None:
    from django.core import mail

    from apps.notifications.services import deliver

    from .helpers import sell_item_to_order

    sell_item_to_order(order, piece)

    Order.objects.filter(pk=order.pk).update(
        payment_status="approved", fulfillment_status="preparing"
    )
    with (
        patch("apps.notifications.services.dispatch"),
        django_capture_on_commit_callbacks(execute=True),
    ):
        transition_status(
            order,
            "fulfillment_status",
            "shipped",
            request=request_for(operator),
            carrier="Transportadora",
        )
    delivery = NotificationDelivery.objects.get()
    deliver(delivery.pk)
    deliver(delivery.pk)
    assert len(mail.outbox) == 1
    assert "Tu pieza va en camino" in mail.outbox[0].subject


@pytest.mark.parametrize(
    "field,value,label",
    [
        ("payment_status", "approved", "Aprobado"),
        ("payment_status", "awaiting_manual_payment", "Pendiente de pago manual"),
        ("payment_status", "expired", "Vencido"),
        ("fulfillment_status", "unfulfilled", "Sin preparar"),
        ("fulfillment_status", "shipped", "Enviado"),
    ],
)
def test_metric_status_labels_preserve_filters(
    order: Order, operator: User, field: str, value: str, label: str
) -> None:
    from urllib.parse import parse_qs, urlsplit

    from django.utils.translation import override

    Order.objects.filter(pk=order.pk).update(**{field: value})
    with override("es"):
        row = compute_metrics()["groups"][field][0]
        assert str(row["label"]) == label
        assert parse_qs(urlsplit(row["url"]).query) == {field: [value]}
        assert row["highlight"] == (value == "awaiting_manual_payment")
        browser = Client()
        browser.force_login(operator)
        response = browser.get(row["url"])
        assert response.status_code == 200
        assert response.context["cl"].result_count == row["count"] == 1


def test_spanish_admin_labels_and_login() -> None:
    from django.apps import apps
    from django.utils.translation import override

    titles = {
        "catalog": "Catálogo",
        "inventory": "Inventario",
        "orders": "Pedidos",
        "payments": "Pagos",
        "promotions": "Promociones",
        "notifications": "Notificaciones",
        "core": "Configuración",
        "cms": "Contenido",
        "accounts": "Cuentas",
        "audit": "Auditoría",
        "cart": "Carritos",
        "pricing": "Precios",
        "axes": "Seguridad de acceso",
        "otp_totp": "Verificación en dos pasos",
    }
    with override("es"):
        for label, title in titles.items():
            config = apps.get_app_config(label)
            assert str(config.verbose_name) == title
            if label not in ("axes", "otp_totp"):
                for model in config.get_models():
                    assert "verbose_name" in model._meta.original_attrs
                    assert "verbose_name_plural" in model._meta.original_attrs
        for model_name, plural in (
            ("catalog.Collection", "colecciones"),
            ("catalog.PieceImage", "imágenes de piezas"),
            ("core.SiteSettings", "configuración del sitio"),
            ("axes.AccessAttempt", "intentos de acceso"),
            ("axes.AccessFailureLog", "fallos de acceso"),
            ("axes.AccessLog", "registros de acceso"),
            ("otp_totp.TOTPDevice", "dispositivos de verificación"),
        ):
            assert str(apps.get_model(model_name)._meta.verbose_name_plural) == plural
        for label in ("axes", "otp_totp"):
            for model in apps.get_app_config(label).get_models():
                if model in site._registry:
                    assert reverse(f"admin:{label}_{model._meta.model_name}_changelist")
        response = Client().get(reverse("admin:login"), HTTP_ACCEPT_LANGUAGE="es")
        assert response.status_code == 200
        html = response.content.decode()
        assert "Volver al sitio" in html
        assert "Iniciar sesión" in html
        assert "Return to site" not in html
        assert "Claro" in html and "Oscuro" in html and "Sistema" in html


def test_order_detail_actions(order: Order, piece: Piece) -> None:
    from .helpers import sell_item_to_order

    sell_item_to_order(order, piece)
    from apps.core.tests.test_dashboard_client import staff

    browser, _ = staff(OPERACIONES)
    order.payment_status = "approved"
    order.fulfillment_status = "preparing"
    order.customer_phone = "3001234567"
    order.save()
    change_url = reverse("admin:orders_order_change", args=[order.pk])
    url = reverse("admin:orders_order_detail_fulfillment", args=[order.pk])
    assert browser.get(url).status_code == 200
    with patch("apps.orders.admin.transition_status", wraps=transition_status) as called:
        response = browser.post(
            url,
            {
                "apply": "1",
                f"expected_{order.pk}": "preparing",
                "target": "shipped",
                "carrier": "Transportadora",
                "tracking_number": "TRACK-123",
                "tracking_url": "https://example.com/track",
            },
        )
    called.assert_called_once()
    assert response.status_code == 302 and response["Location"] == change_url
    order.refresh_from_db()
    assert order.fulfillment_status == "shipped"
    page = browser.get(change_url)
    html = page.content.decode()
    assert "TRACK-123" in html and "https://example.com/track" in html
    assert "detail_manual" not in html
    assert "detail_certificate" not in html
    assert "https://wa.me/573001234567" in html
    response = browser.get(reverse("admin:orders_order_detail_whatsapp", args=[order.pk]))
    assert response["Location"] == "https://wa.me/573001234567"
    order.payment_status = "awaiting_manual_payment"
    order.save()
    assert (
        reverse("admin:orders-confirm-manual", args=[order.pk])
        in browser.get(change_url).content.decode()
    )
    order.payment_status = "approved"
    order.wants_certificate = True
    order.save()
    assert (
        reverse("admin:orders-certificate", args=[order.pk])
        in browser.get(change_url).content.decode()
    )


def test_order_detail_permissions(order: Order) -> None:
    from apps.core.tests.test_dashboard_client import staff

    browser, _ = staff(CONTENIDO)
    assert (
        browser.get(reverse("admin:orders_order_detail_fulfillment", args=[order.pk])).status_code
        == 403
    )
    assert (
        browser.get(reverse("admin:orders_order_detail_manual", args=[order.pk])).status_code == 403
    )


def test_catalog_delete_prevalidates_order_history(order: Order, piece: Piece) -> None:
    from apps.catalog.services import delete_pieces
    from apps.orders.models import OrderItem

    Piece.objects.filter(pk=piece.pk).update(status=Piece.Status.DRAFT)
    other = Piece.objects.create(
        sku="BORRADOR", slug_es="borrador", name_es="Otra", price_cents=10000
    )
    OrderItem.objects.create(
        order=order,
        piece=piece,
        sku=piece.sku,
        name_es=piece.name_es,
        name_en=piece.name_en,
        unit_price_cents=piece.price_cents,
    )
    with pytest.raises(ValidationError, match="tiene pedidos"):
        delete_pieces(Piece.objects.filter(pk__in=[piece.pk, other.pk]))
    assert Piece.objects.filter(pk__in=[piece.pk, other.pk]).count() == 2
