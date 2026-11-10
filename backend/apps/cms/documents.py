"""The document lock is the serialization boundary for every editorial write."""

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from inspect import signature
from zoneinfo import ZoneInfo

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import ContentDocument, Page

_batch = ContextVar("cms_document_batch", default=None)


class ContentConflict(ValidationError):
    def __init__(self, document, *, publishing=False):
        self.document = document
        name = document.updated_by.get_username() if document.updated_by else "otra persona"
        hour = timezone.localtime(document.updated_at, ZoneInfo("America/Bogota")).strftime(
            "%d/%m/%Y %H:%M"
        )
        message = (
            "El borrador cambió desde que lo revisaste. Revisa los cambios antes de publicar."
            if publishing
            else "Otra persona guardó cambios en este contenido mientras editabas "
            f"({name}, {hour}). "
            "Revisa la versión actual antes de guardar."
        )
        super().__init__(message, code="content_conflict")


def require_capability(actor, capability):
    if (
        not actor
        or not actor.is_active
        or not actor.is_staff
        or not actor.has_perm(f"cms.{capability}_content")
    ):
        raise PermissionDenied
    return actor


def document_key(obj=None):
    if isinstance(obj, Page):
        return f"page:{obj.kind}"
    if obj is not None and hasattr(obj, "page_id"):
        return f"page:{obj.page.kind}"
    return "home"


def get_document(key):
    # New pages also get their document in the same transaction as their first save.
    return ContentDocument.objects.get_or_create(key=key)[0]


def lock_document(key):
    get_document(key)
    return (
        ContentDocument.objects.select_for_update(of=("self",))
        .select_related("updated_by")
        .get(key=key)
    )


def check_version(document, expected_version, *, publishing=False):
    # Missing versions must never silently opt out of concurrency control.
    try:
        valid = (
            str(int(expected_version)) == str(expected_version)
            and int(expected_version) == document.draft_version
        )
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise ContentConflict(document, publishing=publishing)


@contextmanager
def admin_batch():
    token = _batch.set({})
    try:
        yield
    finally:
        _batch.reset(token)


def validate_admin_version(key, expected_version):
    document = lock_document(key)
    check_version(document, expected_version)
    state = _batch.get()
    if state is not None:
        state[key] = [document, False]
    return document


@contextmanager
def edit_document(key, actor, expected_version):
    require_capability(actor, "edit")
    with transaction.atomic():
        state = _batch.get()
        if state is not None and key in state:
            document, bumped = state[key]
            yield document
            if not bumped:
                document.draft_version += 1
                document.updated_by = actor
                document.save(update_fields=["draft_version", "updated_by", "updated_at"])
                state[key][1] = True
            return
        document = lock_document(key)
        check_version(document, expected_version)
        token = _batch.set({key: [document, True]})
        try:
            yield document
            document.draft_version += 1
            document.updated_by = actor
            document.save(update_fields=["draft_version", "updated_by", "updated_at"])
        finally:
            _batch.reset(token)


def draft_mutation(key_from_args):
    def decorate(function):
        parameters = signature(function)

        @wraps(function)
        def wrapped(*args, expected_version=None, **kwargs):
            bound = parameters.bind(*args, **kwargs)
            bound.apply_defaults()
            with edit_document(
                key_from_args(*bound.args), bound.arguments.get("actor"), expected_version
            ):
                return function(*args, **kwargs)

        return wrapped

    return decorate
