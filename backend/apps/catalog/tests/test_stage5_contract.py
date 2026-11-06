"""Contrato HTTP público congelado; usa PostgreSQL cuando se configura esa base."""

import pytest
from django.core.exceptions import ValidationError

from apps.catalog import services
from apps.catalog.models import (
    Category,
    Collection,
    CollectionPiece,
    Material,
    PieceImage,
    Stone,
)
from apps.catalog.tests.test_photo_management import photos_for

pytestmark = pytest.mark.django_db
URL = "/api/v1/catalog/pieces"
IMAGE_TYPES = {"src": str, "srcset": str, "width": int, "height": int, "alt": str}
LIST_KEYS = {
    "slug",
    "sku",
    "name",
    "category",
    "stones",
    "price",
    "sale_price",
    "sale_state",
    "is_new",
    "image",
    "hover_image",
}
DETAIL_KEYS = LIST_KEYS | {
    "video",
    "piece_number",
    "short_description",
    "long_description",
    "story",
    "care",
    "attributes",
    "materials",
    "collections",
    "gallery",
    "related",
    "seo",
    "cta",
}
ATTRIBUTES = {
    "ring_size": 7,
    "length_mm": 42.5,
    "metal": "Oro",
    "metal_purity": "18k",
    "carats": 0.4,
    "weight_g": 3.2,
    "dimensions_mm": "12 x 8",
}


def assert_image(image):
    assert image is not None and set(image) == set(IMAGE_TYPES)
    assert all(type(image[key]) is kind for key, kind in IMAGE_TYPES.items())
    assert image["src"] and image["srcset"]


def assert_named(value):
    assert set(value) == {"slug", "name"}
    assert all(type(item) is str for item in value.values())


@pytest.mark.parametrize(
    "locale,root_slug,child_slug,name",
    [
        ("es", "anillos", "solitarios", "Joya especial"),
        ("en", "rings", "solitaires", "Special jewel"),
    ],
)
@pytest.mark.parametrize("ring_size", [7, 7.5, "7½"])
def test_http_contract_filters_search_taxonomy_and_visibility(
    client, make_piece, locale, root_slug, child_slug, name, ring_size
):
    attributes = {**ATTRIBUTES, "ring_size": ring_size}
    root = Category.objects.create(
        name_es="Anillos", name_en="Rings", slug_es="anillos", slug_en="rings"
    )
    child = Category.objects.create(
        name_es="Solitarios",
        name_en="Solitaires",
        slug_es="solitarios",
        slug_en="solitaires",
        parent=root,
    )
    Category.objects.create(name_es="Inactiva", slug_es="inactiva", parent=root, is_active=False)
    stone = Stone.objects.create(
        name_es="Esmeralda", name_en="Emerald", slug_es="esmeralda", slug_en="emerald"
    )
    material = Material.objects.create(name_es="Oro", name_en="Gold", slug_es="oro", slug_en="gold")
    collection = Collection.objects.create(
        name_es="Aurora", name_en="Dawn", slug_es="aurora", slug_en="dawn"
    )
    piece = make_piece(
        published=False,
        category=child,
        name_es="Joya especial",
        name_en="Special jewel",
        attributes=attributes,
        price_cents=12345600,
        sale_price_cents=10000000,
    )
    photos = photos_for(piece, 3)
    for position, status in enumerate(("pending", "failed"), start=3):
        PieceImage.objects.create(
            piece=piece,
            position=position,
            original=photos[0].original.name,
            processing_status=status,
            alt_es="No lista",
        )
    piece.stones.add(stone)
    piece.materials.add(material)
    CollectionPiece.objects.create(piece=piece, collection=collection)
    services.publish_piece(piece, None)
    for state in ("draft", "hidden", "archived"):
        invisible = make_piece(published=False, status=state, category=child)
        photos_for(invisible, 1)
        assert (
            client.get(
                URL + f"/{getattr(invisible, 'slug_' + locale)}", {"locale": locale}
            ).status_code
            == 404
        )
    listing = client.get(URL, {"locale": locale}).json()
    assert set(listing) == {"count", "next", "previous", "results", "facets"}
    assert listing["count"] == 1 and listing["next"] is None and listing["previous"] is None
    card = listing["results"][0]
    assert set(card) == LIST_KEYS
    assert (
        card["name"] == name and card["sale_state"] == "available" and type(card["is_new"]) is bool
    )
    for key in ("image", "hover_image"):
        assert_image(card[key])
    assert_named(card["category"])
    assert_named(card["stones"][0])
    assert card["price"] == {"amount_cents": 12345600, "currency": "COP"}
    assert card["sale_price"] == {"amount_cents": 10000000, "currency": "COP"}
    slug = getattr(piece, "slug_" + locale)
    detail = client.get(URL + f"/{slug}", {"locale": locale}).json()
    assert set(detail) == DETAIL_KEYS
    assert {key: detail[key] for key in LIST_KEYS} == card
    assert detail["attributes"] == attributes
    assert {key: type(value) for key, value in detail["attributes"].items()} == {
        key: type(value) for key, value in attributes.items()
    }
    assert detail["video"] is None and detail["cta"] == {"kind": "add_to_cart"}
    assert len(detail["gallery"]) == 3
    for photo in detail["gallery"]:
        assert_image(photo)
    assert detail["gallery"][0] == card["image"] and detail["gallery"][1] == card["hover_image"]
    assert_named(detail["materials"][0])
    assert_named(detail["collections"][0])
    for filters in (
        {"category": root_slug},
        {"category": child_slug},
        {"q": name},
        {"stone": getattr(stone, "slug_" + locale)},
        {"material": getattr(material, "slug_" + locale)},
        {"collection": getattr(collection, "slug_" + locale)},
    ):
        response = client.get(URL, {"locale": locale, **filters})
        assert response.status_code == 200
        assert [row["sku"] for row in response.json()["results"]] == [piece.sku]
    taxonomy = client.get("/api/v1/catalog/taxonomy", {"locale": locale}).json()
    assert set(taxonomy) == {"categories", "collections", "stones", "materials"}
    category = next(row for row in taxonomy["categories"] if row["slug"] == root_slug)
    assert set(category) == {"slug", "name", "cover", "cover_image", "children"}
    assert category["children"] == [
        {
            "slug": child_slug,
            "name": child.name_en if locale == "en" else child.name_es,
            "cover": None,
            "cover_image": None,
        }
    ]
    assert category["cover"] is None and category["cover_image"] is None
    # Allowed photo reorder/primary swap and removal preserve a public image.
    photos[0].is_primary, photos[1].is_primary, photos[1].is_hover = False, True, False
    photos[0].position, photos[1].position = 1, 0
    services.apply_photo_changes(piece, photos[:2], actor=None)
    updated = client.get(URL + f"/{slug}", {"locale": locale}).json()
    assert_image(updated["image"])
    assert updated["hover_image"] is None and len(updated["gallery"]) == 2
    assert updated["image"] == updated["gallery"][0] == detail["hover_image"]
    with pytest.raises(ValidationError):
        services.apply_photo_changes(piece, [], actor=None)
    assert_image(client.get(URL, {"locale": locale}).json()["results"][0]["image"])


@pytest.mark.parametrize("locale", ["es", "en"])
@pytest.mark.parametrize("state", ["available", "reserved", "sold", "preorder"])
def test_sale_state_visibility_and_null_optional_image(client, make_piece, locale, state):
    piece = make_piece(published=False, status="published", sale_state=state)
    photos_for(piece, 1)
    response = client.get(URL, {"locale": locale, "availability": "all"})
    row = response.json()["results"][0]
    assert row["sale_state"] == state and row["hover_image"] is None and row["sale_price"] is None
    assert_image(row["image"])
    detail = client.get(URL + f"/{getattr(piece, 'slug_' + locale)}", {"locale": locale}).json()
    assert detail["sale_state"] == state and detail["gallery"] == [row["image"]]
    assert detail["attributes"] == {}
    assert detail["cta"]["kind"] == ("add_to_cart" if state == "available" else "whatsapp")
    if state != "available":
        assert detail["cta"]["reason"] == state
    # Existing default excludes sold pieces; availability=all includes them.
    assert client.get(URL, {"locale": locale}).json()["count"] == (0 if state == "sold" else 1)


@pytest.mark.parametrize("locale", ["es", "en"])
def test_taxonomy_covers_contract_and_proportions(client, locale):
    from apps.catalog.tests.conftest import image_file

    for model in (Category, Stone, Collection):
        obj = model(
            name_es="Portada",
            name_en="Cover",
            slug_es="portada",
            slug_en="cover",
            cover_image=image_file(size=(160, 240)),
        )
        services.save_taxonomy(obj)
    data = client.get("/api/v1/catalog/taxonomy", {"locale": locale}).json()
    for group in ("categories", "stones", "collections"):
        taxon = data[group][0]
        assert_image(taxon["cover"])
        assert taxon["cover"]["src"] == taxon["cover_image"]
        assert taxon["cover"]["alt"] == ("Portada" if locale == "es" else "Cover")
        ratio = taxon["cover"]["width"] / taxon["cover"]["height"]
        assert ratio == pytest.approx(16 / 9 if group == "collections" else 2 / 3, abs=0.02)
