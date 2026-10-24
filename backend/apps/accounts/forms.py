from typing import Any

from django.contrib.auth.forms import PasswordResetForm
from django.db import transaction
from django.http import HttpRequest

from apps.audit.services import record


class AuditedPasswordResetForm(PasswordResetForm):
    @transaction.atomic
    def save(self, *args: Any, **kwargs: Any) -> None:
        request: HttpRequest | None = kwargs.get("request")
        # Do not record the submitted address or whether an account matched it.
        record("auth.password_reset_requested", request=request)
        super().save(*args, **kwargs)
