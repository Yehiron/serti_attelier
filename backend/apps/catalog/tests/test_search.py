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
