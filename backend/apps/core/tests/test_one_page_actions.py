from __future__ import annotations

from io import BytesIO
from typing import Any, cast
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.accounts.models import User
from apps.accounts.roles import CONTENIDO, OPERACIONES, PROPIETARIO
from apps.catalog import services
from apps.catalog.models import Category, Piece, PieceImage
from apps.catalog.tests.test_admin_sections import add_data
from apps.cms.models import Page
from apps.core.tests.test_dashboard_client import staff

pytestmark = pytest.mark.django_db


def photo(name: str) -> SimpleUploadedFile:
    data = BytesIO()
    Image.new("RGB", (16, 16)).save(data, "PNG")
    return SimpleUploadedFile(name, data.getvalue(), "image/png")


@pytest.fixture(autouse=True)
def temporary_media(settings: Any, tmp_path: Any) -> None:
    settings.MEDIA_ROOT = str(tmp_path)


def ready_piece() -> Piece:
    piece = Piece.objects.create(
        sku="DETAIL",
        name_es="Anillo",
        name_en="Ring",
        slug_es="anillo",
        short_description_es="Oro",
        price_cents=10000,
        category=Category.objects.create(name_es="Anillos", slug_es="anillos"),
    )
    PieceImage.objects.create(
        piece=piece,
        original=photo("ready.png"),
        alt_es="Anillo",
        is_primary=True,
        processing_status="ready",
    )
    return piece


@pytest.mark.parametrize(
    "operation,state,sale_state,expected,service",
    [
        ("publish", "draft", "available", "published", "publish_piece"),
        ("hide", "published", "available", "hidden", "hide_pieces"),
        ("unhide", "hidden", "available", "published", "unhide"),
        ("archive", "published", "available", "archived", "archive_piece"),
        ("duplicate", "draft", "available", "draft", "duplicate_piece"),
        ("preorder_on", "draft", "available", "draft", "set_preorder"),
        ("preorder_off", "draft", "preorder", "draft", "set_preorder"),
    ],
)
def test_piece_detail(
    operation: str, state: str, sale_state: str, expected: str, service: str
) -> None:
    browser, _ = staff(PROPIETARIO)
    piece = ready_piece()
    Piece.objects.filter(pk=piece.pk).update(status=state, sale_state=sale_state)
    url = reverse(f"admin:catalog_piece_detail_{operation}", args=[piece.pk])
    assert browser.get(url).status_code == 200
    piece.refresh_from_db()
    assert piece.status == state
    target = (
        "apps.catalog.admin.set_preorder"
        if service == "set_preorder"
        else f"apps.catalog.admin.services.{service}"
    )
    function = (
        __import__("apps.inventory.services", fromlist=[service]).set_preorder
        if service == "set_preorder"
        else getattr(services, service)
    )
    with patch(target, wraps=function) as called:
        response = browser.post(url)
    called.assert_called_once()
    assert response.status_code == 302
    target_piece = Piece.objects.exclude(pk=piece.pk).get() if operation == "duplicate" else piece
    assert response["Location"] == reverse("admin:catalog_piece_change", args=[target_piece.pk])
    piece.refresh_from_db()
    assert piece.status == expected
    if operation.startswith("preorder"):
        assert piece.sale_state == ("preorder" if operation == "preorder_on" else "available")
    if operation == "duplicate":
        assert Piece.objects.count() == 2


def test_piece_buttons_and_save_publish() -> None:
    browser, _ = staff(PROPIETARIO)
    piece = ready_piece()
    url = reverse("admin:catalog_piece_change", args=[piece.pk])
    page = browser.get(url)
    assert b"detail_publish" in page.content and b"detail_hide" not in page.content
    data = add_data(page) | {
        "sku": piece.sku,
        "slug_es": piece.slug_es,
        "short_description_es": "Actualizada",
        "category": piece.category_id,
        "catalog_piece_save_publish": "1",
    }
    for inline in page.context["inline_admin_formsets"]:
        for i, form in enumerate(inline.formset.initial_forms):
            data[f"{inline.formset.prefix}-{i}-id"] = form.instance.pk
            for key, value in form.initial.items():
                if value is not None and key != "original":
                    data[f"{inline.formset.prefix}-{i}-{key}"] = value
    response = browser.post(url, data)
    assert response.status_code == 302, (
        response.context["adminform"].form.errors,
        [i.formset.errors for i in response.context["inline_admin_formsets"]],
    )
    piece.refresh_from_db()
    assert piece.status == "published"
    assert cast(Any, piece).short_description_es == "Actualizada"


@pytest.mark.parametrize("add", [True, False])
def test_multiple_upload(add: bool, settings: Any, tmp_path: Any) -> None:
    settings.MEDIA_ROOT = str(tmp_path)
    browser, _ = staff(PROPIETARIO)
    piece = (
        None
        if add
        else Piece.objects.create(
            sku="OLD", name_es="Anillo", name_en="Ring", slug_es="old", price_cents=10000
        )
    )
    url = (
        reverse("admin:catalog_piece_add")
        if add
        else reverse("admin:catalog_piece_change", args=[cast(Piece, piece).pk])
    )
    page = browser.get(url)
    assert b'name="new_photos" multiple' in page.content
    data = add_data(page)
    data["new_photos"] = [
        photo("one.png"),
        SimpleUploadedFile("bad.txt", b"bad"),
        photo("two.png"),
        photo("three.png"),
    ]
    with patch("apps.catalog.tasks.process_piece_image.delay"):
        response = browser.post(url, data, follow=True)
    assert response.status_code == 200
    images = list(PieceImage.objects.order_by("position"))
    assert len(images) == 3
    assert [image.position for image in images] == [0, 1, 2]
    assert [image.is_primary for image in images] == [True, False, False]
    assert all(
        cast(Any, image).alt_es == "Anillo" and cast(Any, image).alt_en == "Ring"
        for image in images
    )
    assert "bad.txt" in response.content.decode()


def test_page_detail_publish() -> None:
    browser, _ = staff(CONTENIDO)
    page = Page.objects.get(kind="terms")
    page.title_es = "Detalle"
    page.body_es = "Texto"
    page.save()
    version = page.version
    url = reverse("admin:cms_page_change", args=[page.pk])
    assert "Cambios sin publicar" in browser.get(url).content.decode()
    response = browser.post(reverse("admin:cms_page_detail_publish", args=[page.pk]))
    assert response.status_code == 302 and response["Location"] == url
    page.refresh_from_db()
    assert page.version == version + 1
    assert "Publicado" in browser.get(url).content.decode()
    page.title_es = "Cambio"
    page.save()
    assert "Cambios sin publicar" in browser.get(url).content.decode()


def test_create_teammate_one_post() -> None:
    browser, _ = staff(PROPIETARIO)
    url = reverse("admin:accounts_user_add")
    assert "Rol" in browser.get(url).content.decode()
    response = browser.post(
        url,
        {
            "first_name": "Ana",
            "last_name": "Pérez",
            "email": "ana@example.com",
            "username": "ana",
            "role": OPERACIONES,
            "is_active": "on",
            "password1": "Complicated-38951!",
            "password2": "Complicated-38951!",
        },
    )
    assert response.status_code == 302
    user = User.objects.get(username="ana")
    assert user.is_staff and not user.is_superuser
    assert user.check_password("Complicated-38951!")
    assert list(user.groups.values_list("name", flat=True)) == [OPERACIONES]
    page = browser.get(reverse("admin:accounts_user_change", args=[user.pk]))
    fields = page.context["adminform"].form.fields
    assert "role" in fields
    assert not {"groups", "user_permissions", "is_superuser", "is_staff"} & fields.keys()


def test_role_escalation_denied() -> None:
    browser, user = staff(OPERACIONES)
    user.user_permissions.add(
        *Permission.objects.filter(
            content_type__app_label="accounts", codename__in=["add_user", "change_user"]
        )
    )
    response = browser.post(
        reverse("admin:accounts_user_add"),
        {
            "username": "bad",
            "email": "bad@example.com",
            "role": PROPIETARIO,
            "password1": "Complicated-38951!",
            "password2": "Complicated-38951!",
            "is_active": "on",
        },
    )
    assert response.status_code == 200
    assert not User.objects.filter(username="bad").exists()
    browser, _ = staff(PROPIETARIO)
    response = browser.post(
        reverse("admin:accounts_user_add"),
        {
            "username": "bad",
            "email": "bad@example.com",
            "role": OPERACIONES,
            "password1": "Complicated-38951!",
            "password2": "Complicated-38951!",
            "is_superuser": "on",
        },
    )
    assert response.status_code == 403
    assert not User.objects.filter(username="bad").exists()


def test_piece_no_permission() -> None:
    browser, user = staff(CONTENIDO)
    piece = ready_piece()
    user.groups.clear()
    assert (
        browser.post(reverse("admin:catalog_piece_detail_publish", args=[piece.pk])).status_code
        == 403
    )


def test_save_publish_failure_keeps_saved_data() -> None:
    browser, _ = staff(PROPIETARIO)
    piece = Piece.objects.create(sku="SAVE", name_es="Antes", slug_es="antes", price_cents=10000)
    url = reverse("admin:catalog_piece_change", args=[piece.pk])
    data = add_data(browser.get(url)) | {"catalog_piece_save_publish": "1"}
    response = browser.post(url, data, follow=True)
    piece.refresh_from_db()
    assert piece.name_es == "Anillo"
    assert piece.status == "draft"
    assert "Falta:" in response.content.decode()


@pytest.mark.parametrize("state", ["draft", "hidden", "published", "archived"])
def test_piece_action_visibility(state: str) -> None:
    browser, _ = staff(PROPIETARIO)
    piece = ready_piece()
    Piece.objects.filter(pk=piece.pk).update(status=state)
    html = browser.get(reverse("admin:catalog_piece_change", args=[piece.pk])).content.decode()
    assert ("/detail_publish/" in html) == (state == "draft")
    assert ("/detail_unhide/" in html) == (state == "hidden")
    assert ("/detail_hide/" in html) == (state == "published")
    assert ("/detail_archive/" in html) == (state != "archived")
    html = browser.get(reverse("admin:catalog_piece_changelist")).content.decode()
    assert (f"/{piece.pk}/detail_publish/" in html) == (state in ("draft", "hidden"))


def test_role_service_rejects_missing_privileges() -> None:
    from django.core.exceptions import PermissionDenied
    from django.test import RequestFactory

    from apps.accounts.services import assign_team_role

    _, actor = staff(OPERACIONES)
    actor.user_permissions.add(*Permission.objects.filter(content_type__app_label="accounts"))
    request = RequestFactory().post("/")
    request.user = actor
    teammate = User.objects.create_user(username="target")
    with pytest.raises(PermissionDenied):
        assign_team_role(teammate, PROPIETARIO, request=request)
    assert not teammate.groups.exists()


def test_password_validation() -> None:
    browser, _ = staff(PROPIETARIO)
    response = browser.post(
        reverse("admin:accounts_user_add"),
        {"username": "weak", "role": OPERACIONES, "password1": "123", "password2": "123"},
    )
    assert response.status_code == 200
    assert response.context["adminform"].form.errors
    assert not User.objects.filter(username="weak").exists()


def test_team_list_uses_role_wording() -> None:
    browser, _ = staff(PROPIETARIO)
    response = browser.get(reverse("admin:accounts_user_changelist"))
    html = response.content.decode()
    assert "Rol" in html
    assert "Grupos" not in html and "superusuario" not in html
    assert "is_staff" not in html and "is_superuser" not in html
