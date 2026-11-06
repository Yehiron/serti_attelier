from unittest.mock import patch

import pytest
from django.core.files.storage import default_storage
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext

from apps.catalog import image_cleanup, services
from apps.catalog.models import PieceImage, Stone
from apps.catalog.tests.test_photo_management import photos_for
from apps.cms.models import HomePublication

pytestmark = pytest.mark.django_db


def test_batch_scan_once_and_preserve_live_and_snapshot_references(
    make_piece, django_capture_on_commit_callbacks
):
    piece = make_piece(published=False)
    photos = photos_for(piece, 6)
    live_path, snapshot_path, obsolete = [photo.original.name for photo in photos[:3]]
    Stone.objects.create(name_es="Compartida", slug_es="compartida", cover_image=live_path)
    # Both the path and the public URL/srcset format are durable publication references.
    HomePublication.objects.create(
        snapshot={"image": {"src": default_storage.url(snapshot_path)}},
        draft_snapshot={"srcset": default_storage.url(photos[3].original.name) + " 480w"},
    )
    with patch.object(
        image_cleanup, "delete_unreferenced", wraps=image_cleanup.delete_unreferenced
    ) as scan:
        with django_capture_on_commit_callbacks(execute=True):
            services.apply_photo_changes(piece, [], actor=None)
        assert scan.call_count == 1
    assert default_storage.exists(live_path)
    assert default_storage.exists(snapshot_path)
    assert default_storage.exists(photos[3].original.name)
    assert not default_storage.exists(obsolete)


def test_batch_rollback_and_failed_nested_operation(make_piece, django_capture_on_commit_callbacks):
    piece = make_piece(published=False)
    photos = photos_for(piece, 3)
    ids = [photo.pk for photo in photos]
    with patch.object(
        image_cleanup, "delete_unreferenced", wraps=image_cleanup.delete_unreferenced
    ) as scan:
        with (
            django_capture_on_commit_callbacks(execute=True),
            pytest.raises(ValueError),
            transaction.atomic(),
        ):
            services.apply_photo_changes(piece, [], actor=None)
            raise ValueError("revertir")
        assert scan.call_count == 0
    assert PieceImage.objects.filter(pk__in=ids).count() == 3
    assert all(default_storage.exists(photo.original.name) for photo in photos)
    # A failed inner scope must not leak paths to the successful parent scope.
    with patch.object(image_cleanup, "delete_unreferenced") as scan:
        with django_capture_on_commit_callbacks(execute=True), image_cleanup.batch_file_cleanup():
            with pytest.raises(ValueError), image_cleanup.batch_file_cleanup():
                image_cleanup.schedule_cleanup({"no-borrar.webp"}, "default")
                raise ValueError("revertir")
            image_cleanup.schedule_cleanup({"borrar.webp"}, "default")
        scan.assert_called_once_with({"borrar.webp"}, "default")


def test_cleanup_query_budget_independent_of_number_of_paths(make_piece):
    piece = make_piece(published=False)
    photos_for(piece, 3)
    with patch.object(default_storage, "delete"):
        with CaptureQueriesContext(connection) as one:
            image_cleanup.delete_unreferenced({"ausente.webp"}, "default")
        with CaptureQueriesContext(connection) as many:
            image_cleanup.delete_unreferenced({f"ausente-{i}.webp" for i in range(30)}, "default")
    assert len(one) == len(many) == len(image_cleanup.IMAGE_MODELS) + 1


def test_six_photo_deletions_scan_queries_before_and_after(
    make_piece, django_capture_on_commit_callbacks
):
    totals = []
    original = image_cleanup.delete_unreferenced

    def measured_scan(paths, using):
        with CaptureQueriesContext(connection) as queries:
            original(paths, using)
        totals.append(len(queries))

    with patch.object(image_cleanup, "delete_unreferenced", measured_scan):
        piece = make_piece(published=False)
        photos = photos_for(piece, 6)
        with django_capture_on_commit_callbacks(execute=True):
            for photo in photos:
                photo.delete()  # comportamiento anterior, un callback por foto
        before = sum(totals)
        assert len(totals) == 6
        totals.clear()
        piece = make_piece(published=False)
        photos_for(piece, 6)
        with django_capture_on_commit_callbacks(execute=True):
            services.apply_photo_changes(piece, [], actor=None)
        after = sum(totals)
        assert len(totals) == 1
    assert before == 54 and after == 9
    print(f"CONSULTAS limpieza 6 fotos: {before} → {after}")
