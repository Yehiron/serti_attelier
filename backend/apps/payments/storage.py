from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import FileSystemStorage
from django.db.models import Model
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateStorage(FileSystemStorage):
    def __init__(self) -> None:
        super().__init__(file_permissions_mode=0o600, directory_permissions_mode=0o700)

    @property
    def base_location(self) -> str:
        return str(settings.PRIVATE_MEDIA_ROOT)

    @property
    def location(self) -> str:
        private = Path(settings.PRIVATE_MEDIA_ROOT).resolve()
        if private.is_relative_to(Path(settings.MEDIA_ROOT).resolve()):
            raise ImproperlyConfigured("PRIVATE_MEDIA_ROOT must be outside MEDIA_ROOT")
        return os.fspath(private)

    def url(self, name: str | None) -> str:
        raise ValueError("Private proofs have no public URL")


def private_storage() -> PrivateStorage:
    return PrivateStorage()


def proof_path(instance: Model, filename: str) -> str:
    return f"payment-proofs/{uuid4().hex}{Path(filename).suffix.lower()}"
