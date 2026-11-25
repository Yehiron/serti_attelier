import pytest
from django.db import connection

from apps.catalog.models import Collection, Piece
from apps.catalog.selectors import filter_pieces

pytestmark = pytest.mark.django_db


def piece(**kwargs):
    defaults = dict(
        sku="SERTI-EM-42",
        name_es="Esmeralda",
        name_en="Emerald",
        slug_es="esmeralda-prueba",
        slug_en="emerald-test",
        status="published",
        price_cents=100000,
        short_description_es="Oro amarillo artesanal",
    )
    return Piece.objects.create(**(defaults | kwargs))


@pytest.mark.postgres
def test_typo_matches_unaccented_name():
    expected = piece(name_es="Esméralda")
    assert connection.vendor == "postgresql"
    assert list(filter_pieces({"q": "esmeralds"}, "es")) == [expected]


def test_search_sku_and_descriptions():
    expected = piece()
    assert list(filter_pieces({"q": "EM-42"}, "es")) == [expected]
    assert list(filter_pieces({"q": "artesanal"}, "es")) == [expected]
    expected.status = "draft"
    expected.save()
    assert not filter_pieces({"q": "EM-42"}, "es").exists()


def test_words_match_across_fields_and_require_every_word():
    expected = piece()
    collection = Collection.objects.create(name_es="Bosque", slug_es="bosque-prueba")
    expected.collections.add(collection)
    assert list(filter_pieces({"q": "esmeralda amarillo bosque"}, "es")) == [expected]
    assert not filter_pieces({"q": "esmeralda platino"}, "es").exists()


@pytest.mark.postgres
def test_search_matches_expected_fields_and_order(client, make_piece):
    from apps.catalog.models import Category, Material, Stone

    category = Category.objects.create(name_es="Orfebrería", slug_es="orfebreria")
    stone = Stone.objects.create(name_es="Turquesa", slug_es="turquesa")
    material = Material.objects.create(name_es="Platino", slug_es="platino")
    collection = Collection.objects.create(name_es="Constelación", slug_es="constelacion")
    name = make_piece(name_es="Zafiro singular", sku="NAME-100")
    newer_name = make_piece(name_es="Zafiro singular", sku="NAME-101")
    sku = make_piece(name_es="Modelo neutro", sku="CODIGO-XYZ")
    category_piece = make_piece(name_es="Modelo categórico", category=category)
    stone_piece = make_piece(name_es="Modelo mineral")
    material_piece = make_piece(name_es="Modelo metálico")
    collection_piece = make_piece(name_es="Modelo celeste")
    stone_piece.stones.add(stone)
    material_piece.materials.add(material)
    collection_piece.collections.add(collection)
    cases = [
        ("zafiro", [newer_name, name]),
        ("CODIGO-XYZ", [sku]),
        ("orfebreria", [category_piece]),
        ("turquesa", [stone_piece]),
        ("platino", [material_piece]),
        ("constelación", [collection_piece]),
        ("constelacion", [collection_piece]),
        ("modelo turquesa", [stone_piece]),
        ("inexistenteabc", []),
    ]
    for query, expected in cases:
        response = client.get("/api/v1/catalog/pieces", {"q": query, "locale": "es"})
        assert response.status_code == 200
        assert [item["sku"] for item in response.json()["results"]] == [p.sku for p in expected]


@pytest.mark.postgres
def test_search_text_is_resolved_once(client, make_piece, django_assert_max_num_queries):
    from django.test.utils import CaptureQueriesContext

    make_piece(name_es="Esmeralda")
    with django_assert_max_num_queries(8), CaptureQueriesContext(connection) as queries:
        response = client.get("/api/v1/catalog/pieces", {"q": "esmeralda"})
        assert response.status_code == 200
        assert response.json()["count"] == 1
    assert 1 <= sum("catalog_immutable_unaccent" in query["sql"].lower() for query in queries) <= 2
