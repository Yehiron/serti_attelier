import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings

from apps.cms.publishing import pending_changes
from apps.orders.selectors import legal_versions

pytestmark = pytest.mark.django_db


def test_refuses_without_debug():
    with override_settings(DEBUG=False), pytest.raises(CommandError):
        call_command("e2e_publish_cms")


@override_settings(DEBUG=True)
def test_publishes_legal_pages_and_leaves_no_drafts():
    call_command("e2e_publish_cms")
    call_command("e2e_publish_cms")  # idempotent
    assert all(legal_versions().values())
    assert pending_changes("home")["count"] == 0
