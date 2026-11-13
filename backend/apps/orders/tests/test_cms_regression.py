"""CMS publications must leave commercial data and quotes exactly unchanged."""

from copy import deepcopy

import pytest

from apps.accounts.roles import PROPIETARIO
from apps.cms import brand, services, visual_documents
from apps.cms.documents import edit_document, get_document
from apps.cms.menus import publish_menu
from apps.cms.models import Page
from apps.core.tests.test_dashboard_client import staff
from apps.inventory.models import PieceReservation
from apps.orders.models import Order
from apps.payments.models import PaymentAttempt

pytestmark = pytest.mark.django_db


def test_editorial_publish_preserves_cart_quote_stock_and_reservation(client, piece, payload):
    from .test_checkout import add, submit

    _, owner = staff(PROPIETARIO)
    add(client, piece)
    # Keep one existing reservation/order while exercising a separate cart.
    other = type(client)()
    from apps.catalog.models import Piece

    reserved = Piece.objects.create(
        sku="CMS-RESERVED",
        name_es="Reservada",
        slug_es="cms-reserved",
        price_cents=97000,
        status="published",
    )
    add(other, reserved)
    payload["payment_channel"] = "manual"
    assert submit(other, payload).status_code == 201
    cart = deepcopy(client.get("/api/v1/cart").data)
    quote = deepcopy(
        client.post("/api/v1/checkout/quote", {"wants_certificate": False}, format="json").data
    )
    assert "total_cents" in quote
    models = [Piece, PieceReservation, Order, PaymentAttempt]
    before = {m: list(m.objects.order_by("pk").values()) for m in models}
    for key, section, values in [
        ("brand:identity", "brand", {"wine": "#6a1f36", "title_font": "cormorant"}),
        ("home", "seo", {"title": {"es": "Portada de prueba CMS"}}),
    ]:
        doc = get_document(key)
        if key == brand.KEY and not doc.brand_identity:
            doc.brand_identity = deepcopy(brand.DEFAULT)
            doc.save()
        with edit_document(key, owner, doc.draft_version):
            visual_documents.mutate(key, "update", {"id": section, "values": values}, owner, None)
        version = get_document(key).draft_version
        if key == brand.KEY:
            brand.publish(owner, expected_version=version)
        else:
            services.publish_home(owner, expected_version=version)
    key = "menu:main"
    doc = get_document(key)
    with edit_document(key, owner, doc.draft_version):
        doc.menu_items = [
            {
                "visible": True,
                "link": {"kind": "home", "label": {"es": "Inicio nuevo", "en": "New home"}},
            }
        ]
        doc.save(update_fields=["menu_items"])
    publish_menu(key, owner, expected_version=get_document(key).draft_version)
    page, _ = Page.objects.get_or_create(
        kind="shipping", defaults={"title_es": "Envíos", "slug_es": "envios-cms"}
    )
    services.publish_page(page, owner, expected_version=get_document("page:shipping").draft_version)
    assert client.get("/api/v1/cart").data == cart
    assert (
        client.post("/api/v1/checkout/quote", {"wants_certificate": False}, format="json").data
        == quote
    )
    assert {m: list(m.objects.order_by("pk").values()) for m in models} == before
    # The original cart still checks out with the very same price.
    assert submit(client, payload).status_code == 201
    assert Order.objects.latest("pk").total_cents == quote["total_cents"]
