"""Permanent internal redirects. All graph mutations serialize on the home lock."""

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.audit.services import record
from apps.core.routes import ROUTES

from .documents import check_version, lock_document, require_capability
from .models import Page, Redirect
from .page_options import internal_path, snapshot_path

CACHE_KEY = "cms:active-redirects:v1"


def active_redirects():
    rows = cache.get(CACHE_KEY)
    if rows is None:
        rows = list(
            Redirect.objects.filter(is_active=True).values("from_path", "to_path", "status_code")
        )
        cache.set(CACHE_KEY, rows, 60)
    return rows


def invalidate_redirects():
    # Cache failure after commit must never report a committed publication as failed.
    from .invalidation import enqueue

    transaction.on_commit(lambda: cache.delete(CACHE_KEY), robust=True)
    enqueue(["cms:redirects"], document_key="redirects")


def destination_exists(path):
    lang, tail = path.split("/")[1], path.split("/")[2:]
    if not tail:
        return True
    if len(tail) == 1 and tail[0] in {
        ROUTES[key][lang == "en"] for key in ("catalog", "cart", "checkout", "wishlist", "search")
    }:
        return True
    pages = list(Page.objects.prefetch_related("revisions"))
    for kind, route in (
        ("personalize", "personalize"),
        ("manufacturer", "story"),
        ("contact", "contact"),
    ):
        if tail == [ROUTES[route][lang == "en"]] and not any(
            p.kind == kind and p.version for p in pages
        ):
            return True
    for page in pages:
        revision = next(iter(page.revisions.all()), None)
        if revision and snapshot_path(page, revision.snapshot, lang) == path:
            return True
    if len(tail) == 2:
        from apps.catalog.models import Category, Collection, Piece, Stone

        for key, model in (
            ("category", Category),
            ("collection", Collection),
            ("stone", Stone),
            ("piece", Piece),
        ):
            if tail[0] == ROUTES[key][lang == "en"]:
                rows = model.objects.all()
                if key == "piece":
                    rows = rows.filter(status="published")
                return rows.filter(**{f"slug_{lang}": tail[1]}).exists()
    return False


def flatten(rows):
    active = {row.from_path: row for row in rows if row.is_active}
    for start, row in active.items():
        seen = {start}
        target = row.to_path
        while target in active:
            if target in seen:
                raise ValidationError("Estas direcciones formarían un bucle. Elige otro destino.")
            seen.add(target)
            target = active[target].to_path
        if target == start:
            raise ValidationError("Una dirección no puede redirigir a sí misma.")
        row.to_path = target
    return rows


@transaction.atomic
def save_redirect(obj, actor, request=None, *, expected_version=None):
    require_capability(actor, "publish")
    lock_document("home")
    document = lock_document("redirects")
    check_version(document, expected_version)
    obj.from_path = internal_path(obj.from_path)
    obj.to_path = internal_path(obj.to_path)
    obj.locale = obj.from_path.split("/")[1]
    rows = list(Redirect.objects.select_for_update(of=("self",)).exclude(pk=obj.pk))
    flatten([*rows, obj])
    if obj.is_active and not destination_exists(obj.to_path):
        raise ValidationError("El destino no existe en la tienda publicada.")
    # A working page cannot be shadowed by a manual redirect.
    if obj.is_active and destination_exists(obj.from_path):
        raise ValidationError("La dirección anterior todavía pertenece a una página de la tienda.")
    if not obj.pk:
        obj.created_by = actor
    obj.full_clean()
    obj.save()
    for row in rows:
        row.save(update_fields=["to_path"])
    document.draft_version += 1
    document.updated_by = actor
    document.save(update_fields=["draft_version", "updated_by", "updated_at"])
    invalidate_redirects()
    record("cms.redirect_saved", actor=actor, obj=obj, request=request)
    return obj


def on_page_publish(page, previous, snapshot, actor):
    # Caller holds home then page document locks in this order.
    transitions = []
    for lang in ("es", "en"):
        target = snapshot_path(page, snapshot, lang)
        old = snapshot_path(page, previous.snapshot, lang) if previous else target
        if old and target and old != target:
            transitions.append((lang, old, target))
    if not transitions:
        return
    rows = list(Redirect.objects.select_for_update(of=("self",)))
    original = {row.pk: (row.to_path, row.is_active, row.status_code, row.origin) for row in rows}
    by_path = {row.from_path: row for row in rows}
    for lang, old, target in transitions:
        # Republishing an old address makes it live again before flattening chains.
        if target in by_path:
            by_path[target].is_active = False
        row = by_path.get(old)
        if row is None:
            row = Redirect(from_path=old, locale=lang, created_by=actor, origin="automatic")
            rows.append(row)
            by_path[old] = row
        row.to_path, row.is_active, row.status_code, row.origin = target, True, 301, "automatic"
    flatten(rows)
    for row in rows:
        current = (row.to_path, row.is_active, row.status_code, row.origin)
        if row.pk is None or current != original[row.pk]:
            row.full_clean()
            row.save()
    invalidate_redirects()
