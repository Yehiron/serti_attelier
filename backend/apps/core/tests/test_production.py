from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.cms.tests.helpers import cms_version
from apps.core import health
from apps.core.management.commands.check_production import wompi_coherent


@pytest.mark.parametrize("mode", ["test", "prod"])
def test_wompi_coherence(mode: str) -> None:
    host = "sandbox" if mode == "test" else "production"
    with override_settings(
        WOMPI_API_URL=f"https://{host}.wompi.co/v1",
        WOMPI_PUBLIC_KEY=f"pub_{mode}_abc",
        WOMPI_PRIVATE_KEY=f"prv_{mode}_abc",
        WOMPI_INTEGRITY_SECRET=f"{mode}_integrity_abc",
        WOMPI_EVENTS_SECRET=f"{mode}_events_abc",
    ):
        assert wompi_coherent()
        with override_settings(
            WOMPI_EVENTS_SECRET="test_events_wrong" if mode == "prod" else "prod_events_wrong"
        ):
            assert not wompi_coherent()


def test_production_reports_failures_without_database() -> None:
    out = StringIO()
    with (
        patch.object(health, "check_database", return_value=False),
        patch.object(health, "check_redis", return_value=False),
        patch.object(health, "check_migrations", return_value=False),
        override_settings(
            DEBUG=True,
            ALLOWED_HOSTS=["*"],
            PUBLIC_SITE_URL="http://example.com",
            INTERNAL_API_TOKEN="",
        ),
        pytest.raises(CommandError),
    ):
        call_command("check_production", stdout=out)
    assert "❌ DEBUG" in out.getvalue()
    assert "❌ Redis" in out.getvalue()


@pytest.mark.django_db
def test_production_can_pass_with_warnings() -> None:
    from django.contrib.auth.models import Group
    from django_otp.plugins.otp_totp.models import TOTPDevice

    from apps.accounts.models import User
    from apps.cms.models import Page
    from apps.cms.services import publish_page

    user = User.objects.create(
        username="owner",
        email="owner@example.com",
        is_active=True,
        is_staff=True,
        is_superuser=True,
    )
    user.groups.add(Group.objects.get_or_create(name="Propietario")[0])
    TOTPDevice.objects.create(user=user, confirmed=True)
    for kind in ("terms", "privacy"):
        page = Page.objects.get(kind=kind)
        publish_page(page, actor=user, expected_version=cms_version(page))
    out = StringIO()
    with (
        patch.object(health, "check_database", return_value=True),
        patch.object(health, "check_redis", return_value=True),
        patch.object(health, "check_migrations", return_value=True),
        patch("apps.core.management.commands.check_production.wompi_coherent", return_value=True),
        override_settings(
            SECRET_KEY="abcdefghij0123456789" * 4,
            ALLOWED_HOSTS=["example.com"],
            COUPON_EMAIL_PEPPER="p" * 32,
            INTERNAL_API_TOKEN="t" * 32,
        ),
    ):
        call_command("check_production", stdout=out)
    assert "❌" not in out.getvalue()
    assert "⚠️" in out.getvalue()
