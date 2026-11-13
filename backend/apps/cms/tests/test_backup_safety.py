"""Offline guard checks: no database, Docker or decryption key is required."""

import subprocess
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.migrations.exceptions import IrreversibleError

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "infra/scripts"
if not SCRIPTS.is_dir():
    SCRIPTS = Path("/infra/scripts")


@pytest.mark.parametrize("script", ["restore.sh", "backup-verify.sh", "backup-verify-restore.sh"])
def test_restore_requires_explicit_flag(script):
    # No flag: each entry point must fail before any destructive command.
    result = subprocess.run(  # noqa: S603 — fixed test scripts
        ["/bin/sh", str(SCRIPTS / script)], capture_output=True, timeout=5
    )
    assert result.returncode == 2


def test_verify_refuses_real_database_without_connecting(tmp_path):
    with pytest.raises(CommandError, match="Solo se permite"):
        call_command(
            "verify_backup",
            database_name="production",
            media_root=str(tmp_path),
            private_media_root=str(tmp_path),
        )


def test_outbox_reverse_refuses_audit_loss():
    migration = import_module("apps.cms.migrations.0027_cacheinvalidation")
    model = MagicMock()
    apps = SimpleNamespace(get_model=lambda *args: model)
    editor = SimpleNamespace(connection=SimpleNamespace(alias="default"))
    model.objects.using.return_value.exists.return_value = True
    with pytest.raises(IrreversibleError):
        migration.protect_outbox(apps, editor)
    model.objects.using.return_value.exists.return_value = False
    migration.protect_outbox(apps, editor)
