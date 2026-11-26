import pytest

from apps.catalog.models import Piece
from apps.catalog.services import save_piece
from apps.cms.models import Redirect

pytestmark = pytest.mark.django_db


@pytest.fixture
def piece():
    return Piece.objects.create(
        sku="SLUG-REDIRECT",
        name_es="Joya",
        slug_es="joya",
        slug_en="jewel",
        price_cents=10000,
        status=Piece.Status.PUBLISHED,
    )


def save_slugs(piece, es, en):
    piece.slug_es, piece.slug_en = es, en
    save_piece(piece, actor=None)


def test_published_slug_changes_create_localized_redirects(piece):
    save_slugs(piece, "nueva", "new")
    assert set(Redirect.objects.values_list("from_path", "to_path", "status_code")) == {
        ("/es/piezas/joya", "/es/piezas/nueva", 301),
        ("/en/pieces/jewel", "/en/pieces/new", 301),
    }


def test_redirect_chains_are_flattened(piece):
    save_slugs(piece, "segunda", "second")
    save_slugs(piece, "tercera", "third")
    assert Redirect.objects.get(from_path="/es/piezas/joya").to_path == "/es/piezas/tercera"
    assert Redirect.objects.get(from_path="/en/pieces/jewel").to_path == "/en/pieces/third"


def test_return_to_old_slug_does_not_loop(piece):
    save_slugs(piece, "segunda", "second")
    save_slugs(piece, "joya", "jewel")
    assert not Redirect.objects.get(from_path="/es/piezas/joya").is_active
    assert Redirect.objects.get(from_path="/es/piezas/segunda").to_path == "/es/piezas/joya"
    assert not Redirect.objects.get(from_path="/en/pieces/jewel").is_active


def test_draft_slug_changes_do_not_create_redirects(piece):
    Piece.objects.filter(pk=piece.pk).update(status=Piece.Status.DRAFT)
    piece.refresh_from_db()
    save_slugs(piece, "borrador", "draft")
    assert not Redirect.objects.exists()
