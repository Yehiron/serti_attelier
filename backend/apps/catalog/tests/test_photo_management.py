from unittest.mock import patch

import pytest
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from apps.accounts.roles import CONTENIDO, PROPIETARIO
from apps.audit.models import AuditLog
from apps.catalog import services
from apps.catalog.api.serializers import PieceDetailSerializer
from apps.catalog.models import PieceImage
from apps.catalog.tests.test_operating_rules import change_data
from apps.core.tests.test_dashboard_client import staff

from .conftest import image_file

pytestmark = pytest.mark.django_db


def photos_for(piece, count=3):
    return [
        PieceImage.objects.create(
            piece=piece,
            original=image_file(size=(16, 16)),
            alt_es=f"Foto {i}",
            position=i,
            is_primary=i == 0,
            is_hover=i == 1,
            processing_status="ready",
            renditions={"webp": {"480": f"pieces/renditions/{i}.webp"}},
        )
        for i in range(count)
    ]


def flags(data, images, primary=0, hover=1):
    for i in range(len(images)):
        data.pop(f"images-{i}-is_primary", None)
        data.pop(f"images-{i}-is_hover", None)
        if i == primary:
            data[f"images-{i}-is_primary"] = "on"
        if i == hover:
            data[f"images-{i}-is_hover"] = "on"


@pytest.mark.parametrize("order", [[1, 0], [2, 1, 0]])
@pytest.mark.parametrize("role", [PROPIETARIO, CONTENIDO])
def test_inline_reorder(make_piece, order, role):
    browser, _ = staff(role)
    piece = make_piece(published=False)
    images = photos_for(piece, len(order))
    url, data = change_data(browser, piece)
    for i, position in enumerate(order):
        data[f"images-{i}-position"] = position
    response = browser.post(url, data)
    assert response.status_code == 302, response.context and response.context["errors"]
    assert list(piece.images.values_list("pk", flat=True)) == [images[i].pk for i in order]
    log = AuditLog.objects.get(action="catalog.photos_updated")
    assert log.actor_id and log.object_id == str(piece.pk) and "orden" in log.diff


@pytest.mark.parametrize("source,target", [(0, 2), (2, 0), (0, 1)])
@pytest.mark.parametrize("role", [PROPIETARIO, CONTENIDO])
def test_inline_primary_and_hover_swap(make_piece, source, target, role):
    browser, _ = staff(role)
    piece = make_piece(published=False)
    images = photos_for(piece)
    piece.images.update(is_primary=False, is_hover=False)
    piece.images.filter(pk=images[source].pk).update(is_primary=True)
    piece.images.filter(pk=images[target].pk).update(is_hover=True)
    url, data = change_data(browser, piece)
    flags(data, images, primary=target, hover=source)
    response = browser.post(url, data)
    assert response.status_code == 302, response.context and response.context["errors"]
    assert piece.images.get(is_primary=True).pk == images[target].pk
    assert piece.images.get(is_hover=True).pk == images[source].pk
    assert {"principal", "hover"} <= AuditLog.objects.get(
        action="catalog.photos_updated"
    ).diff.keys()


@pytest.mark.parametrize("invalid", ["primary", "hover", "both", "none", "position"])
def test_invalid_final_state_is_form_error(make_piece, invalid):
    browser, _ = staff(PROPIETARIO)
    piece = make_piece(published=False)
    images = photos_for(piece)
    url, data = change_data(browser, piece)
    if invalid == "primary":
        data["images-2-is_primary"] = "on"
    elif invalid == "hover":
        data["images-2-is_hover"] = "on"
    elif invalid == "both":
        data["images-0-is_hover"] = "on"
    elif invalid == "none":
        flags(data, images, primary=-1)
    else:
        data["images-1-position"] = 0
    response = browser.post(url, data)
    assert response.status_code == 200
    assert response.context["errors"]
    assert piece.images.get(is_primary=True).pk == images[0].pk
    assert piece.images.count() == 3


@pytest.mark.parametrize("status", ["pending", "failed"])
@pytest.mark.parametrize("published", [False, True])
def test_primary_processing_policy(make_piece, status, published):
    browser, _ = staff(PROPIETARIO)
    piece = make_piece(published=False)
    images = photos_for(piece)
    piece.images.filter(pk=images[2].pk).update(processing_status=status)
    if published:
        type(piece).objects.filter(pk=piece.pk).update(status="published")
    url, data = change_data(browser, piece)
    flags(data, images, primary=2, hover=1)
    with patch("apps.catalog.tasks.process_piece_image.delay"):
        response = browser.post(url, data)
    assert response.status_code == (200 if published else 302)
    if published:
        assert services.PUBLISHED_PHOTO_MESSAGE in response.content.decode()
    assert piece.images.get(is_primary=True).pk == images[0 if published else 2].pk


@pytest.mark.parametrize("count", [1, 3])
@pytest.mark.parametrize("published", [False, True])
def test_delete_primary_or_last(make_piece, count, published):
    browser, _ = staff(PROPIETARIO)
    piece = make_piece(published=False)
    images = photos_for(piece, count)
    if published:
        type(piece).objects.filter(pk=piece.pk).update(status="published")
    url, data = change_data(browser, piece)
    data["images-0-DELETE"] = "on"
    # Drafts may delete a primary, choosing a replacement if photos remain.
    if count > 1 and not published:
        flags(data, images, primary=2, hover=1)
    response = browser.post(url, data)
    assert response.status_code == (200 if published else 302)
    assert piece.images.count() == (count if published else count - 1)
    if published:
        assert services.PUBLISHED_PHOTO_MESSAGE in response.content.decode()
    else:
        assert "borradas" in AuditLog.objects.get(action="catalog.photos_updated").diff


def test_content_cannot_delete(make_piece):
    browser, actor = staff(CONTENIDO)
    piece = make_piece(published=False)
    images = photos_for(piece)
    url, data = change_data(browser, piece)
    data["images-2-DELETE"] = "on"
    assert browser.post(url, data).status_code == 302
    assert piece.images.count() == 3
    with pytest.raises(ValidationError, match="permiso para borrar"):
        services.apply_photo_changes(piece, images[:2], actor=actor)


def test_status_shape_and_privacy(make_piece):
    browser, _ = staff(CONTENIDO)
    piece = make_piece(published=False)
    images = photos_for(piece)
    piece.images.filter(pk=images[1].pk).update(
        processing_status="failed", error="/private/secret traceback"
    )
    piece.images.filter(pk=images[2].pk).update(processing_status="pending")
    url = reverse("admin:catalog_piece_photo_status", args=[piece.pk])
    response = browser.get(url)
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"photos", "ready_to_publish", "missing"}
    assert data["ready_to_publish"] is True
    assert len(data["photos"]) == 3
    for row in data["photos"]:
        assert set(row) == {"id", "status", "thumb_url", "is_primary", "is_hover", "message"}
        assert row["status"] in {"ready", "pending", "failed"}
        if row["status"] != "ready":
            assert row["thumb_url"] is None
    assert "secret" not in response.content.decode()
    for image in images:
        assert image.original.name not in response.content.decode()
    assert browser.post(url).status_code == 405
    assert (
        browser.get(reverse("admin:catalog_piece_photo_status", args=[999999])).status_code == 404
    )
    assert Client().get(url).status_code == 302


def test_endpoint_permissions_and_scope(make_piece):
    browser, actor = staff(CONTENIDO)
    piece = make_piece(published=False)
    images = photos_for(piece)
    status_url = reverse("admin:catalog_piece_photo_status", args=[piece.pk])
    retry_url = reverse("admin:catalog_piece_photo_retry", args=[piece.pk, images[1].pk])
    actor.groups.clear()
    assert browser.get(status_url).status_code == 403
    assert browser.post(retry_url).status_code == 403
    actor.user_permissions.add(Permission.objects.get(codename="view_piece"))
    assert browser.get(status_url).status_code == 200
    assert browser.post(retry_url).status_code == 403
    piece_admin = admin.site._registry[type(piece)]
    with patch.object(piece_admin, "get_queryset", return_value=type(piece).objects.none()):
        assert browser.get(status_url).status_code == 404


def test_retry_csrf_ownership_and_task(make_piece, django_capture_on_commit_callbacks):
    browser, _ = staff(CONTENIDO)
    piece = make_piece(published=False)
    images = photos_for(piece)
    other = make_piece(published=False)
    image = photos_for(other, 1)[0]
    url = reverse("admin:catalog_piece_photo_retry", args=[piece.pk, images[1].pk])
    assert browser.get(url).status_code == 405
    assert (
        browser.post(
            reverse("admin:catalog_piece_photo_retry", args=[piece.pk, image.pk])
        ).status_code
        == 404
    )
    csrf_browser = Client(enforce_csrf_checks=True)
    csrf_browser.cookies = browser.cookies
    assert csrf_browser.post(url).status_code == 403
    piece.images.filter(pk=images[1].pk).update(processing_status="failed", error="error")
    page = csrf_browser.get(reverse("admin:catalog_piece_change", args=[piece.pk]))
    assert b"Reintentar" in page.content and b"photo-status.js" in page.content
    with patch("apps.catalog.tasks.process_piece_image.delay") as task:
        with django_capture_on_commit_callbacks(execute=True):
            response = csrf_browser.post(
                url, {"csrfmiddlewaretoken": csrf_browser.cookies["csrftoken"].value}
            )
            assert response.status_code == 302
            task.assert_not_called()
        task.assert_called_once_with(images[1].pk)
    images[1].refresh_from_db()
    assert images[1].processing_status == "pending" and images[1].error == ""
    with patch("apps.catalog.tasks.process_piece_image.delay") as task:
        with django_capture_on_commit_callbacks(execute=True):
            assert browser.post(url, HTTP_ACCEPT="application/json").json() == {"status": "pending"}
        task.assert_not_called()


def test_public_contract_after_reorder(make_piece):
    piece = make_piece(published=False)
    images = photos_for(piece)
    before = PieceDetailSerializer(piece, context={"locale": "es"}).data
    for image in images:
        image.position = 2 - image.position
    services.apply_photo_changes(piece, images, actor=None)
    after = PieceDetailSerializer(
        type(piece).objects.get(pk=piece.pk), context={"locale": "es"}
    ).data
    assert after["image"] == before["image"]
    assert after["hover_image"] == before["hover_image"]
    assert after["gallery"] == list(reversed(before["gallery"]))


def test_published_can_append_and_reject_replacement(make_piece):
    browser, _ = staff(PROPIETARIO)
    piece = make_piece(published=True)
    url, data = change_data(browser, piece)
    from apps.core.tests.test_one_page_actions import photo

    data["new_photos"] = photo("nueva.png")
    with patch("apps.catalog.tasks.process_piece_image.delay"):
        assert browser.post(url, data).status_code == 302
    assert piece.images.count() == 2
    url, data = change_data(browser, piece)
    data["images-0-original"] = photo("principal.png")
    response = browser.post(url, data)
    assert response.status_code == 200
    assert services.PUBLISHED_PHOTO_MESSAGE in response.content.decode()


def test_normalization_and_hidden_primary(make_piece):
    piece = make_piece(published=False, status="hidden")
    images = photos_for(piece)
    for index, photo in enumerate(images):
        photo.position = (3 - index) * 10
        photo.is_primary = index == 2
    piece.images.filter(pk=images[2].pk).update(processing_status="failed")
    services.apply_photo_changes(piece, images, actor=None)
    assert list(piece.images.values_list("position", flat=True)) == [0, 1, 2]
    assert piece.images.get(is_primary=True).processing_status == "failed"


def test_atomic_rollback_and_cleanup(make_piece, django_capture_on_commit_callbacks):
    from django.core.files.storage import default_storage
    from django.db import transaction

    piece = make_piece(published=False)
    images = photos_for(piece)
    removed_pk, path = images[2].pk, images[2].original.name
    images[0].position, images[1].position = 1, 0
    with (
        django_capture_on_commit_callbacks(execute=True),
        pytest.raises(ValueError),
        transaction.atomic(),
    ):
        services.apply_photo_changes(piece, images[:2], actor=None)
        assert default_storage.exists(path)
        raise ValueError("rollback")
    assert piece.images.count() == 3
    assert list(piece.images.values_list("pk", flat=True)) == [p.pk for p in images]
    assert not AuditLog.objects.filter(action="catalog.photos_updated").exists()
    with django_capture_on_commit_callbacks(execute=True):
        services.apply_photo_changes(piece, images[:2], actor=None)
        assert default_storage.exists(path)
    assert not default_storage.exists(path)
    assert not piece.images.filter(pk=removed_pk).exists()


def test_worker_state_preserved_and_metadata_does_not_enqueue(
    make_piece, django_capture_on_commit_callbacks
):
    piece = make_piece(published=False)
    images = photos_for(piece)
    piece.images.filter(pk=images[2].pk).update(processing_status="pending", renditions={})
    with patch("apps.catalog.tasks.process_piece_image.delay") as task:
        with django_capture_on_commit_callbacks(execute=True):
            services.apply_photo_changes(piece, images, actor=None)
        task.assert_not_called()
    images[2].refresh_from_db()
    assert images[2].processing_status == "pending" and images[2].renditions == {}


def test_published_can_choose_ready_replacement(make_piece):
    browser, _ = staff(PROPIETARIO)
    piece = make_piece(published=False)
    images = photos_for(piece)
    type(piece).objects.filter(pk=piece.pk).update(status="published")
    url, data = change_data(browser, piece)
    data["images-0-DELETE"] = "on"
    flags(data, images, primary=2, hover=1)
    assert browser.post(url, data).status_code == 302
    assert piece.images.count() == 2
    assert piece.images.get(is_primary=True).pk == images[2].pk
