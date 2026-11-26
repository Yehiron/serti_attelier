import io
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from PIL import Image

from apps.accounts.roles import PROPIETARIO
from apps.audit.models import AuditLog
from apps.catalog.models import Category
from apps.core.tests.test_dashboard_client import staff

pytestmark = pytest.mark.django_db


def payload(**values):
    return {
        "name_es": "Anillos",
        "description_es": "Hechos a mano",
        "is_active": "on",
        "position": "0",
        **values,
    }


def test_list_panel_save_create_and_errors(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    browser, user = staff(PROPIETARIO)
    category = Category.objects.create(name_es="Antes", slug_es="antes")
    url = reverse("admin:catalog_category_changelist")
    response = browser.get(url + f"?category={category.pk}")
    assert response.status_code == 200 and response.context["selected"].pk == category.pk
    image = io.BytesIO()
    Image.new("RGB", (80, 80), "red").save(image, format="PNG")
    data = payload(
        cover_image=SimpleUploadedFile("cover.png", image.getvalue(), content_type="image/png")
    )
    response = browser.post(url + f"?category={category.pk}", data)
    assert response.status_code == 302 and response.url.endswith(f"?category={category.pk}")
    category.refresh_from_db()
    assert (
        category.name_es == "Anillos"
        and category.description_es == "Hechos a mano"
        and category.is_active
        and category.cover_image
    )
    assert AuditLog.objects.filter(actor=user, object_id=str(category.pk)).exists()
    response = browser.post(url + f"?category={category.pk}", payload(name_es=""))
    assert response.status_code == 200 and response.context["pane_form"].errors
    response = browser.post(
        url + f"?category={category.pk}",
        payload(cover_image=SimpleUploadedFile("bad.png", b"bad", content_type="image/png")),
    )
    assert "cover_image" in response.context["pane_form"].errors
    response = browser.post(url + "?category=new", payload(name_es="Aretes"))
    assert response.status_code == 302 and Category.objects.filter(name_es="Aretes").exists()


def test_reorder_requires_csrf_and_keeps_siblings_together():
    browser, _ = staff(PROPIETARIO)
    first = Category.objects.create(name_es="A", slug_es="a")
    second = Category.objects.create(name_es="B", slug_es="b")
    child = Category.objects.create(name_es="C", slug_es="c", parent=first)
    secure = Client(enforce_csrf_checks=True)
    secure.cookies = browser.cookies
    secure.get(reverse("admin:catalog_category_changelist"))
    url = reverse("admin:catalog_category_reorder")
    data = {"ids": json.dumps([second.pk, first.pk])}
    assert secure.post(url, data).status_code == 403
    data["csrfmiddlewaretoken"] = secure.cookies["csrftoken"].value
    assert secure.post(url, data).status_code == 200
    first.refresh_from_db()
    second.refresh_from_db()
    assert second.position < first.position
    data["ids"] = json.dumps([first.pk, child.pk])
    assert secure.post(url, data).status_code == 400


def test_view_only_cannot_save_or_reorder():
    from django.contrib.auth.models import Permission

    browser, user = staff(PROPIETARIO)
    user.groups.clear()
    user.user_permissions.add(Permission.objects.get(codename="view_category"))
    category = Category.objects.create(name_es="Anillos", slug_es="anillos")
    url = reverse("admin:catalog_category_changelist") + f"?category={category.pk}"
    assert browser.get(url).status_code == 200
    assert browser.post(url, payload()).status_code == 403
    assert (
        browser.post(
            reverse("admin:catalog_category_reorder"), {"ids": json.dumps([category.pk])}
        ).status_code
        == 403
    )
