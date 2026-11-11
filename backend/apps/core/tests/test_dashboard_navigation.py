"""Sidebar section selection needs no database or CMS publication."""

from types import SimpleNamespace

import pytest
from django.test import RequestFactory
from django.urls import reverse

from apps.core.dashboard import NAVIGATION


@pytest.mark.parametrize(
    ("route", "document", "expected"),
    [
        ("visual-editor", "", "Editor visual"),
        ("visual-editor", "home:home", "Editor visual"),
        ("visual-editor", "page:story", "Editor visual"),
        ("visual-editor", "menu:main", "Menús"),
        ("visual-editor", "menu:footer", "Menús"),
        ("visual-editor", "brand:identity", "Identidad de marca"),
        ("cms-redirect-management", "", "Redirecciones"),
        ("cms-translations", "", "Traducciones pendientes"),
    ],
)
def test_web_navigation_selects_only_current_section(route, document, expected):
    request = RequestFactory().get(reverse(route), {"document": document})
    entries = [entry for group in NAVIGATION for entry in group["items"] if "active" in entry]
    assert [str(entry["title"]) for entry in entries if entry["active"](request)] == [expected]


@pytest.mark.parametrize("can_edit", [True, False])
def test_identity_navigation_requires_content_permission(can_edit):
    identity = next(
        entry
        for group in NAVIGATION
        for entry in group["items"]
        if str(entry["title"]) == "Identidad de marca"
    )
    request = RequestFactory().get("/")
    request.user = SimpleNamespace(has_perm=lambda name: can_edit and name == "cms.edit_content")
    assert identity["permission"](request) is can_edit
    assert str(identity["link"]) == f"{reverse('visual-editor')}?document=brand:identity"
