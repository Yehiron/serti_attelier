"""Transactional cache outbox; saving a draft never calls this module."""

import logging

from django.db import transaction

from .models import CacheInvalidation

logger = logging.getLogger(__name__)


def enqueue(tags, *, document_key=""):
    row = CacheInvalidation.objects.create(tags=sorted(set(tags)), document_key=document_key)
    transaction.on_commit(lambda: dispatch(row.pk), robust=True)
    return row


def dispatch(pk):
    from .tasks import revalidate_tags

    try:
        row = CacheInvalidation.objects.get(pk=pk)
    except Exception:
        logger.warning("Actualización CMS pendiente (registro %s).", pk)
        return
    try:
        # First attempt inline (bounded 5 s timeout) so the very next storefront visit
        # after "Publicar" is fresh; the task records the outcome on the row.
        revalidate_tags.run(row.tags, invalidation_id=pk)
        return
    except Exception:
        pass  # Recorded as pending by the task; retries continue in Celery below.
    try:
        revalidate_tags.apply_async((row.tags,), {"invalidation_id": pk}, countdown=30)
    except Exception:
        # Never include exception text: transport errors can contain credentials.
        logger.warning("Actualización CMS pendiente (registro %s).", pk)


def publication_saved(sender, instance, created, raw=False, **kwargs):
    if raw or not created:
        return
    name = sender.__name__
    if name == "HomePublication":
        key, tags = "home", ["cms:home"]
    elif name == "PageRevision":
        key = f"page:{instance.page.kind}"
        # Pages are destinations of menus, home cards, legal links and redirects.
        tags = [
            f"cms:{key}",
            "cms:pages",
            "cms:home",
            "cms:menu:main",
            "cms:menu:footer",
            "cms:settings",
            "cms:redirects",
        ]
    elif name == "MenuPublication":
        key = f"menu:{instance.menu}"
        tags = [f"cms:{key}"]
    else:
        key, tags = "brand:identity", ["cms:brand"]
    enqueue(tags, document_key=key)


def live_saved(sender, instance, raw=False, **kwargs):
    if raw:
        return
    name = sender.__name__
    if name == "SiteSettings":
        enqueue(["cms:settings"], document_key="settings")
    elif name == "PersonalizationService":
        enqueue(["cms:personalization"], document_key="personalization")
    else:
        # Taxonomy names, covers and URLs also appear in published home/menu snapshots.
        enqueue(["cms:home", "cms:menu:main", "cms:menu:footer", "catalog"], document_key="catalog")


def catalog_relations_changed(sender, instance, action, **kwargs):
    if action in {"post_add", "post_remove", "post_clear"}:
        live_saved(sender, instance)
