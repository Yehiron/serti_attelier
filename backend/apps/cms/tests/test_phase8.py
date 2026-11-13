"""PostgreSQL integration for the transactional cache outbox; no network required."""

from copy import deepcopy
from unittest.mock import MagicMock, patch

import pytest
from celery.exceptions import Retry
from django.db import transaction
from django.test import override_settings

from apps.accounts.roles import PROPIETARIO
from apps.cms import brand
from apps.cms.documents import get_document
from apps.cms.invalidation import enqueue
from apps.cms.models import (
    BrandPublication,
    CacheInvalidation,
    HomePublication,
    MenuPublication,
    Page,
    PageRevision,
)
from apps.cms.tasks import revalidate_tags
from apps.core.tests.test_dashboard_client import staff

pytestmark = pytest.mark.django_db


def test_enqueue_after_commit_only(django_capture_on_commit_callbacks):
    # First attempt runs inline after commit so the next visit is fresh.
    with (
        patch("apps.cms.tasks.revalidate_tags.run") as run,
        patch("apps.cms.tasks.revalidate_tags.apply_async") as later,
    ):
        with django_capture_on_commit_callbacks(execute=True), transaction.atomic():
            row = enqueue(["cms:home", "cms:home"])
            run.assert_not_called()
        run.assert_called_once_with(["cms:home"], invalidation_id=row.pk)
        later.assert_not_called()


def test_inline_failure_falls_back_to_celery_retry(django_capture_on_commit_callbacks):
    with (
        patch("apps.cms.tasks.revalidate_tags.run", side_effect=RuntimeError) as run,
        patch("apps.cms.tasks.revalidate_tags.apply_async") as later,
    ):
        with django_capture_on_commit_callbacks(execute=True), transaction.atomic():
            row = enqueue(["cms:home"])
        run.assert_called_once()
        later.assert_called_once_with(
            (["cms:home"],), {"invalidation_id": row.pk}, countdown=30
        )


def test_rollback_discards_outbox_and_callback(django_capture_on_commit_callbacks):
    before = CacheInvalidation.objects.count()
    with patch("apps.cms.tasks.revalidate_tags.run") as run:
        with (
            django_capture_on_commit_callbacks(execute=True),
            pytest.raises(ValueError),
            transaction.atomic(),
        ):
            enqueue(["cms:home"])
            raise ValueError
        run.assert_not_called()
    assert CacheInvalidation.objects.count() == before


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("home", ["cms:home"]),
        ("brand", ["cms:brand"]),
        ("menu", ["cms:menu:footer"]),
        (
            "page",
            [
                "cms:page:shipping",
                "cms:pages",
                "cms:home",
                "cms:menu:main",
                "cms:menu:footer",
                "cms:settings",
                "cms:redirects",
            ],
        ),
    ],
)
def test_publication_tags(kind, expected):
    before = CacheInvalidation.objects.count()
    if kind == "home":
        HomePublication.objects.create(snapshot={})
    elif kind == "brand":
        BrandPublication.objects.create(snapshot=deepcopy(brand.DEFAULT))
    elif kind == "menu":
        MenuPublication.objects.create(menu="footer", snapshot=[])
    else:
        page, _ = Page.objects.get_or_create(kind="shipping", defaults={"slug_es": "envios-fase8"})
        PageRevision.objects.create(page=page, version=page.version + 100, snapshot={})
    assert CacheInvalidation.objects.count() == before + 1
    assert CacheInvalidation.objects.latest("pk").tags == sorted(expected)


def test_draft_restore_and_republish_idempotence():
    _, owner = staff(PROPIETARIO)
    doc = get_document(brand.KEY)
    if not doc.brand_identity:
        doc.brand_identity = deepcopy(brand.DEFAULT)
        doc.save()
    first = brand.publish(owner, expected_version=doc.draft_version)
    before = CacheInvalidation.objects.count()
    assert brand.publish(owner, expected_version=doc.draft_version).pk == first.pk
    brand.restore(first, owner, expected_version=doc.draft_version)
    doc.refresh_from_db()
    assert CacheInvalidation.objects.count() == before
    assert brand.publish(owner, expected_version=doc.draft_version).pk == first.pk
    assert CacheInvalidation.objects.count() == before


@override_settings(
    REVALIDATE_SECRET="secret-must-not-appear", FRONTEND_INTERNAL_URL="http://frontend:3000"
)
def test_delivery_retry_sanitized_and_idempotent(caplog):
    row = enqueue(["cms:brand"])
    with patch("urllib.request.build_opener") as opener:
        opener.return_value.open.side_effect = OSError("secret-must-not-appear")
        with pytest.raises(Retry):
            revalidate_tags.apply(args=[row.tags], kwargs={"invalidation_id": row.pk}, throw=True)
    row.refresh_from_db()
    assert row.state == "pending" and row.attempts == 1
    assert "secret-must-not-appear" not in caplog.text
    response = MagicMock(status=200)
    response.read.return_value = b'{"ok":true}'
    with patch("urllib.request.build_opener") as opener:
        opener.return_value.open.return_value.__enter__.return_value = response
        revalidate_tags.run(row.tags, invalidation_id=row.pk)
        revalidate_tags.run(row.tags, invalidation_id=row.pk)
        assert opener.return_value.open.call_count == 1
        req = opener.return_value.open.call_args.args[0]
        assert req.get_header("X-revalidate-secret") == "secret-must-not-appear"
    row.refresh_from_db()
    assert row.state == "sent"


def test_exhausted_and_broker_failure(caplog, django_capture_on_commit_callbacks):
    with (
        patch("apps.cms.tasks.revalidate_tags.run", side_effect=RuntimeError("transport-secret")),
        patch(
            "apps.cms.tasks.revalidate_tags.apply_async",
            side_effect=RuntimeError("transport-secret"),
        ),
        django_capture_on_commit_callbacks(execute=True),
    ):
        row = enqueue(["cms:home"])
    assert row.state == "pending" and "transport-secret" not in caplog.text
    row.attempts = 5
    row.save()
    with override_settings(REVALIDATE_SECRET=""):
        revalidate_tags.run(row.tags, invalidation_id=row.pk)
    row.refresh_from_db()
    assert row.state == "failed" and row.attempts == 6


@pytest.mark.parametrize(
    "model", ["SiteSettings", "PersonalizationService", "Category", "Collection", "Stone"]
)
def test_live_saves_invalidate(model):
    from django.apps import apps

    app = (
        "core"
        if model == "SiteSettings"
        else "cms"
        if model == "PersonalizationService"
        else "catalog"
    )
    cls = apps.get_model(app, model)
    obj = cls.objects.first()
    if obj is None:
        obj = (
            cls.objects.create()
            if model == "SiteSettings"
            else cls.objects.create(
                **(
                    {"title_es": "Fase 8"}
                    if model == "PersonalizationService"
                    else {"name_es": "Fase 8", "slug_es": "fase8"}
                )
            )
        )
    before = CacheInvalidation.objects.count()
    obj.save()
    assert CacheInvalidation.objects.count() == before + 1
    tags = CacheInvalidation.objects.latest("pk").tags
    assert (
        tags == ["cms:settings"]
        if model == "SiteSettings"
        else tags == ["cms:personalization"]
        if model == "PersonalizationService"
        else {"cms:home", "catalog"} <= set(tags)
    )


def test_redirect_changes_and_retry_recovery(django_capture_on_commit_callbacks):
    from datetime import timedelta

    from django.utils import timezone

    from apps.cms.models import Redirect
    from apps.cms.redirects import save_redirect
    from apps.cms.tasks import retry_pending_revalidations

    _, owner = staff(PROPIETARIO)
    redirect = Redirect(from_path="/es/antigua-fase8", to_path="/es")
    save_redirect(redirect, owner, expected_version=get_document("redirects").draft_version)
    assert CacheInvalidation.objects.latest("pk").tags == ["cms:redirects"]
    redirect.is_active = False
    save_redirect(redirect, owner, expected_version=get_document("redirects").draft_version)
    assert CacheInvalidation.objects.latest("pk").tags == ["cms:redirects"]
    row = enqueue(["cms:home"])
    CacheInvalidation.objects.filter(pk=row.pk).update(
        updated_at=timezone.now() - timedelta(minutes=16)
    )
    with patch("apps.cms.invalidation.dispatch") as dispatch:
        retry_pending_revalidations.run()
    dispatch.assert_called_once_with(row.pk)


@pytest.mark.django_db(transaction=True)
def test_outbox_migration_idempotent_and_safe_reverse():
    from django.db import connection
    from django.db.migrations.exceptions import IrreversibleError
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    leaves = executor.loader.graph.leaf_nodes()
    counts = {m: m.objects.count() for m in [HomePublication, PageRevision, BrandPublication]}
    # Data belongs to this isolated migration test, never to a developer database.
    CacheInvalidation.objects.all().delete()
    row = CacheInvalidation.objects.create(tags=["cms:home"])
    try:
        with pytest.raises(IrreversibleError):
            executor.migrate([("cms", "0026_initial_brand")])
        assert CacheInvalidation.objects.filter(pk=row.pk).exists()
        row.delete()
        MigrationExecutor(connection).migrate([("cms", "0026_initial_brand")])
        MigrationExecutor(connection).migrate(leaves)
        MigrationExecutor(connection).migrate(leaves)
        assert CacheInvalidation.objects.count() == 0
        assert {m: m.objects.count() for m in counts} == counts
    finally:
        MigrationExecutor(connection).migrate(leaves)


def test_catalog_piece_changes_expire_home_and_catalog():
    from apps.catalog.models import Piece

    piece = Piece.objects.create(sku="CMS8", name_es="Prueba", slug_es="cms8", price_cents=10000)
    row = CacheInvalidation.objects.latest("pk")
    assert {"cms:home", "catalog"} <= set(row.tags)
    # The stock transition hook invalidates presentation only, without changing its data.
    before = CacheInvalidation.objects.count()
    piece.sale_state = "reserved"
    piece.save(update_fields=["sale_state"])
    assert CacheInvalidation.objects.count() == before + 1
    piece.refresh_from_db()
    assert piece.price_cents == 10000 and piece.sale_state == "reserved"


def test_snapshot_path_tolerates_empty_legacy_snapshot():
    from apps.cms.models import Page
    from apps.cms.page_options import snapshot_path

    page = Page(kind="terms", slug_es="terminos")
    assert snapshot_path(page, {}, "es") is None
    assert snapshot_path(page, {"es": {}}, "es") is None
    assert snapshot_path(page, {"es": {"slug": "terminos"}}, "es")
