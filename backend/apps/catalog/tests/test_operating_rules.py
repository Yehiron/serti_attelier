from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.accounts.roles import CONTENIDO, PROPIETARIO
from apps.catalog import services
from apps.catalog.models import Piece, PieceImage
from apps.catalog.tests.test_admin_sections import add_data
from apps.core.tests.test_dashboard_client import staff
from apps.core.tests.test_one_page_actions import photo, ready_piece

pytestmark = pytest.mark.django_db
OPERATIONS = ["publish", "hide", "unhide", "archive", "preorder_on", "preorder_off", "duplicate"]


def change_data(browser, piece):
    url = reverse("admin:catalog_piece_change", args=[piece.pk])
    page = browser.get(url)
    data = add_data(page) | {
        "sku": piece.sku,
        "slug_es": piece.slug_es,
        "category": piece.category_id,
        "short_description_es": "Descripción nueva",
    }
    for inline in page.context["inline_admin_formsets"]:
        for i, form in enumerate(inline.formset.initial_forms):
            data[f"{inline.formset.prefix}-{i}-id"] = form.instance.pk
            for key, value in form.initial.items():
                if value is not None and key != "original":
                    data[f"{inline.formset.prefix}-{i}-{key}"] = value
    return url, data


@pytest.mark.parametrize("viewer", [False, True])
@pytest.mark.parametrize("operation", OPERATIONS)
def test_no_commercial_posts(viewer, operation):
    browser, user = staff(CONTENIDO)
    if viewer:
        user.groups.clear()
        user.user_permissions.add(Permission.objects.get(codename="view_piece"))
    piece = ready_piece()
    detail = browser.post(reverse(f"admin:catalog_piece_detail_{operation}", args=[piece.pk]))
    assert detail.status_code == 403
    browser.post(
        reverse("admin:catalog_piece_changelist"),
        {
            "action": operation,
            "_selected_action": [piece.pk],
        },
    )
    piece.refresh_from_db()
    assert piece.status == "draft" and piece.sale_state == "available"
    assert Piece.objects.count() == 1
    assert (
        browser.post(
            reverse("admin:catalog_piece_change", args=[piece.pk]),
            {
                "catalog_piece_save_publish": "1",
            },
        ).status_code
        == 403
    )


def test_content_access_and_edit(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    browser, user = staff(CONTENIDO)
    assert not user.has_perm("catalog.add_piece")
    assert browser.get(reverse("admin:catalog_piece_add")).status_code == 403
    for url in [reverse("admin:index"), reverse("admin:catalog_piece_changelist")]:
        assert "Agregar pieza" not in browser.get(url).content.decode()
    piece = ready_piece()
    url, data = change_data(browser, piece)
    data["new_photos"] = photo("nueva.png")
    with patch("apps.catalog.tasks.process_piece_image.delay"):
        response = browser.post(url, data)
    assert response.status_code == 302
    piece.refresh_from_db()
    assert piece.short_description_es == "Descripción nueva"
    assert piece.price_cents == 10000
    assert piece.images.count() == 2


@pytest.mark.parametrize("source", list(Piece.Status.values))
@pytest.mark.parametrize(
    "target,operation",
    [
        ("published", "publish"),
        ("published", "unhide"),
        ("hidden", "hide"),
        ("archived", "archive"),
    ],
)
@pytest.mark.parametrize("route", ["detail", "bulk", "save"])
def test_transition_routes(source, target, operation, route):
    if route == "save" and operation != "publish":
        pytest.skip("Guardar y publicar solo tiene destino publicada")
    browser, _ = staff(PROPIETARIO)
    piece = ready_piece()
    Piece.objects.filter(pk=piece.pk).update(status=source)
    piece.refresh_from_db()
    allowed = target in services.EDITORIAL_TRANSITIONS[source]
    if operation == "unhide":
        allowed = allowed and source == "hidden"
    if route == "detail":
        browser.post(reverse(f"admin:catalog_piece_detail_{operation}", args=[piece.pk]))
    elif route == "bulk":
        browser.post(
            reverse("admin:catalog_piece_changelist"),
            {
                "action": operation,
                "_selected_action": [piece.pk],
            },
        )
    else:
        url, data = change_data(browser, piece)
        browser.post(url, data | {"catalog_piece_save_publish": "1"})
    piece.refresh_from_db()
    assert piece.status == (target if allowed else source)


@pytest.mark.parametrize("source", list(Piece.Status.values))
@pytest.mark.parametrize("target", list(Piece.Status.values))
def test_matrix_all_pairs(source, target):
    if target in services.EDITORIAL_TRANSITIONS[source]:
        services.validate_editorial_transition(source, target)
    else:
        with pytest.raises(ValidationError):
            services.validate_editorial_transition(source, target)


def test_bulk_results_and_atomic_delete():
    browser, _ = staff(PROPIETARIO)
    good = ready_piece()
    bad = Piece.objects.create(
        sku="SIN-CATEGORIA", name_es="Incompleta", slug_es="incompleta", price_cents=10000
    )
    url = reverse("admin:catalog_piece_changelist")
    response = browser.post(url, {"action": "publish", "_selected_action": [good.pk, bad.pk]})
    text = " ".join(str(m) for m in get_messages(response.wsgi_request))
    assert "1 pieza publicada" in text and bad.sku in text and "categoría" in text
    response = browser.post(
        url,
        {
            "action": "delete_selected",
            "_selected_action": [good.pk, bad.pk],
            "post": "yes",
        },
    )
    assert Piece.objects.filter(pk__in=[good.pk, bad.pk]).count() == 2
    assert "No se borró ninguna" in " ".join(str(m) for m in get_messages(response.wsgi_request))


@pytest.mark.parametrize("route", ["detail", "bulk"])
def test_duplicate_destination(route):
    browser, _ = staff(PROPIETARIO)
    piece = ready_piece()
    if route == "detail":
        response = browser.post(reverse("admin:catalog_piece_detail_duplicate", args=[piece.pk]))
    else:
        response = browser.post(
            reverse("admin:catalog_piece_changelist"),
            {
                "action": "duplicate",
                "_selected_action": [piece.pk],
            },
        )
    copy = Piece.objects.exclude(pk=piece.pk).get()
    assert response["Location"] == reverse("admin:catalog_piece_change", args=[copy.pk])
    text = " ".join(str(m) for m in get_messages(response.wsgi_request))
    assert copy.sku in text and "Las fotos no se copian" in text
    assert not copy.images.exists()


@pytest.mark.parametrize("hook", ["save_piece", "save_piece_relations", "save_piece_image"])
def test_service_errors_render_form(hook):
    browser, _ = staff(PROPIETARIO)
    piece = ready_piece()
    url, data = change_data(browser, piece)
    # A changed inline reaches save_formset.
    data["images-0-alt_es"] = "Texto nuevo"
    with patch(
        f"apps.catalog.admin.services.{hook}",
        side_effect=ValidationError("Una pieza no puede relacionarse consigo misma."),
    ):
        response = browser.post(url, data)
    assert response.status_code == 200
    assert "consigo misma" in str(response.context["adminform"].form.errors)
    piece.refresh_from_db()
    assert piece.short_description_es == "Oro"


def test_self_relation_form_error():
    browser, _ = staff(PROPIETARIO)
    piece = ready_piece()
    url, data = change_data(browser, piece)
    response = browser.post(url, data | {"related": [piece.pk]})
    assert response.status_code == 200
    assert "consigo misma" in str(response.context["adminform"].form.errors)


def test_save_publish_pending(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    browser, _ = staff(PROPIETARIO)
    piece = ready_piece()
    PieceImage.objects.filter(piece=piece).delete()
    url, data = change_data(browser, piece)
    data |= {"catalog_piece_save_publish": "1", "new_photos": photo("pendiente.png")}
    with patch("apps.catalog.tasks.process_piece_image.delay"):
        response = browser.post(url, data)
    assert response.status_code == 302
    piece.refresh_from_db()
    assert piece.status == "draft" and piece.short_description_es == "Descripción nueva"
    assert "Las fotos se están procesando" in " ".join(
        str(m) for m in get_messages(response.wsgi_request)
    )


@pytest.mark.parametrize("sale_state", ["sold", "reserved"])
def test_delete_blocks_sale_state(sale_state):
    piece = ready_piece()
    Piece.objects.filter(pk=piece.pk).update(sale_state=sale_state)
    with pytest.raises(ValidationError, match="vendida o reservada"):
        services.delete_piece(piece)


def test_role_sync_removes_old_add():
    from django.contrib.auth.models import Group

    from apps.accounts.services import sync_roles

    sync_roles()
    group = Group.objects.get(name=CONTENIDO)
    group.permissions.add(Permission.objects.get(codename="add_piece"))
    sync_roles()
    assert not group.permissions.filter(codename="add_piece").exists()
    assert not group.permissions.filter(codename="publish_piece").exists()
    assert Group.objects.get(name=PROPIETARIO).permissions.filter(codename="publish_piece").exists()


@pytest.mark.parametrize("granted", ["change_piece", "publish_piece"])
def test_commercial_requires_both_permissions(granted):
    browser, user = staff(CONTENIDO)
    user.groups.clear()
    user.user_permissions.add(Permission.objects.get(codename=granted))
    piece = ready_piece()
    response = browser.get(reverse("admin:catalog_piece_changelist"))
    if response.status_code == 200:
        action_form = response.context["action_form"]
        assert action_form is None or "publish" not in dict(action_form.fields["action"].choices)
    browser.post(
        reverse("admin:catalog_piece_changelist"),
        {
            "action": "publish",
            "_selected_action": [piece.pk],
        },
    )
    piece.refresh_from_db()
    assert piece.status == "draft"


@pytest.mark.parametrize("hook", ["save_piece", "save_piece_relations", "save_piece_image"])
def test_domain_error_renders_form(hook):
    from apps.core.exceptions import PublicationError

    browser, _ = staff(PROPIETARIO)
    piece = ready_piece()
    url, data = change_data(browser, piece)
    data["images-0-alt_es"] = "Texto nuevo"
    with patch(
        f"apps.catalog.admin.services.{hook}", side_effect=PublicationError("Revisa la pieza.")
    ):
        response = browser.post(url, data)
    assert response.status_code == 200
    assert "Revisa la pieza" in str(response.context["adminform"].form.errors)


def test_price_permission_service_error_renders_form():
    from django.core.exceptions import PermissionDenied

    browser, _ = staff(CONTENIDO)
    piece = ready_piece()
    url, data = change_data(browser, piece)
    with patch(
        "apps.catalog.admin.services.save_piece",
        side_effect=PermissionDenied("No tienes permiso para cambiar precios."),
    ):
        response = browser.post(url, data)
    assert response.status_code == 200
    assert "No tienes permiso para cambiar precios" in str(
        response.context["adminform"].form.errors
    )


@pytest.mark.parametrize("history_only", [False, True])
def test_delete_checks_reservations_and_history(history_only):
    from datetime import timedelta

    from django.utils import timezone

    from apps.inventory.models import PieceReservation
    from apps.inventory.services import release_reservation, reserve_piece

    piece = ready_piece()
    other = Piece.objects.create(sku="OTRA", slug_es="otra", name_es="Otra", price_cents=10000)
    reservation = reserve_piece(
        piece.pk,
        kind=PieceReservation.Kind.MANUAL,
        reference="manual",
        expires_at=timezone.now() + timedelta(minutes=30),
    )
    if history_only:
        release_reservation(reservation.pk, reason="reservation_expired")
    with pytest.raises(ValidationError, match="tiene reservas"):
        services.delete_pieces(Piece.objects.filter(pk__in=[piece.pk, other.pk]))
    assert Piece.objects.filter(pk__in=[piece.pk, other.pk]).count() == 2


def test_view_only_cannot_delete_bulk():
    browser, user = staff(CONTENIDO)
    user.groups.clear()
    user.user_permissions.add(Permission.objects.get(codename="view_piece"))
    piece = ready_piece()
    browser.post(
        reverse("admin:catalog_piece_changelist"),
        {
            "action": "delete_selected",
            "_selected_action": [piece.pk],
            "post": "yes",
        },
    )
    assert Piece.objects.filter(pk=piece.pk).exists()


def test_save_publish_add_pending(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    browser, _ = staff(PROPIETARIO)
    url = reverse("admin:catalog_piece_add")
    data = add_data(browser.get(url)) | {
        "catalog_piece_save_publish": "1",
        "new_photos": photo("pendiente.png"),
    }
    with patch("apps.catalog.tasks.process_piece_image.delay"):
        response = browser.post(url, data)
    assert response.status_code == 302
    piece = Piece.objects.get(sku=data["sku"])
    assert piece.status == "draft" and piece.images.exists()
    assert "Las fotos se están procesando" in " ".join(
        str(m) for m in get_messages(response.wsgi_request)
    )
