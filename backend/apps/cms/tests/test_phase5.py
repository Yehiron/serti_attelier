"""Library regression proof. DB cases deliberately require PostgreSQL."""

import hashlib
import json
import os
from copy import deepcopy
from datetime import timedelta
from importlib import import_module
from io import BytesIO
from unittest.mock import patch

import pytest
from celery.exceptions import Retry
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.accounts.roles import CONTENIDO, OPERACIONES, PROPIETARIO
from apps.audit.models import AuditLog
from apps.cms import media, selectors, services
from apps.cms.documents import get_document
from apps.cms.management.commands.cleanup_cms_media import collect
from apps.cms.models import HomeSection, MediaAsset
from apps.cms.tasks import render_media
from apps.cms.tests.helpers import historical_public_bytes
from apps.core.tests.test_dashboard_client import staff


def photo(fmt="PNG", size=(160, 200), exif=False):
    output = BytesIO()
    image = Image.new("RGB", size, "#b56375")
    kwargs = {}
    if exif:
        metadata = Image.Exif()
        metadata[270] = "GPS private metadata"
        kwargs["exif"] = metadata
    image.save(output, format=fmt, **kwargs)
    return SimpleUploadedFile("nombre-personal.jpg", output.getvalue(), "image/jpeg")


@pytest.mark.parametrize(
    "focal,crops",
    [
        ((-0.1, 0.5), {}),
        ((float("nan"), 0.5), {}),
        ((True, 0.5), {}),
        ((0.5, 0.5), {"2:3": {}}),
        ((0.5, 0.5), {"4:5": {"x": 0.8, "y": 0, "w": 0.5, "h": 0.5}}),
        ((0.5, 0.5), {"4:5": {"x": 0, "y": 0, "w": 1, "h": 0.5}}),
        ((0.5, 0.5), {"4:5": {"x": 0, "y": 0, "w": 0, "h": 0}}),
    ],
)
def test_invalid_adjustments(focal, crops):
    with pytest.raises(ValidationError):
        media.validate_adjustments(*focal, crops, 160, 200)


def test_valid_crop_and_focal():
    media.validate_adjustments(0, 1, {"4:5": {"x": 0, "y": 0, "w": 1, "h": 1}}, 160, 200)


@pytest.fixture
def owner(db, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return staff(PROPIETARIO)


def ready_asset(user, django_capture_on_commit_callbacks, **kwargs):
    with django_capture_on_commit_callbacks(execute=True):
        asset, duplicate = media.upload(photo(**kwargs), user)
    asset.refresh_from_db()
    asset.alt_es, asset.alt_en = "Foto de taller", "Workshop photo"
    asset.version += 1
    asset.save()
    render_media.apply(args=(asset.pk, asset.version)).get()
    asset.refresh_from_db()
    assert not duplicate
    return asset


@pytest.mark.django_db
def test_upload_strips_metadata_hash_duplicates_renditions(
    owner, django_capture_on_commit_callbacks
):
    _, user = owner
    asset = ready_asset(user, django_capture_on_commit_callbacks, fmt="JPEG", exif=True)
    assert "nombre-personal" not in asset.original.name
    with asset.original.open("rb") as file:
        image = Image.open(file)
        assert not image.getexif()
        assert "exif" not in image.info
    duplicate, existing = media.upload(photo(fmt="JPEG", exif=True), user)
    assert existing and duplicate.pk == asset.pk
    assert asset.state == "ready"
    for ratio in media.ratios():
        rendered = media.resolve(media.reference(asset, ratio), "en")
        a, b = map(float, ratio.split(":"))
        assert abs(rendered["width"] / rendered["height"] - a / b) < 0.02
        assert rendered["alt"] == "Workshop photo"
        assert rendered["srcset"] and "nombre-personal" not in rendered["src"]
        assert rendered["focal"] == {"x": 0.5, "y": 0.5}


@pytest.mark.parametrize(
    "upload",
    [
        SimpleUploadedFile("false.jpg", b"not an image", "image/jpeg"),
        SimpleUploadedFile("photo.svg", b'<svg xmlns="http://www.w3.org/2000/svg"/>', "image/jpeg"),
    ],
)
@pytest.mark.django_db
def test_invalid_file(owner, upload):
    with pytest.raises(ValidationError):
        media.upload(upload, owner[1])


@pytest.mark.django_db
def test_limits_bytes_and_pixels(owner):
    file = photo()
    file.size = 26 * 1024 * 1024
    with pytest.raises(ValidationError, match="25 MB"):
        media.upload(file, owner[1])
    with (
        patch("apps.catalog.images.MAX_PIXELS", 100),
        pytest.raises(ValidationError, match="40 megapíxeles"),
    ):
        media.upload(photo(), owner[1])
    with patch("PIL.Image.MAX_IMAGE_PIXELS", 100), pytest.raises(ValidationError):
        media.upload(photo(), owner[1])


@pytest.mark.parametrize(
    "role,allowed", [(PROPIETARIO, True), (CONTENIDO, True), (OPERACIONES, False)]
)
@pytest.mark.django_db
def test_library_roles(role, allowed, settings, tmp_path, django_capture_on_commit_callbacks):
    settings.MEDIA_ROOT = tmp_path
    browser, _ = staff(role)
    assert browser.get(reverse("cms-media")).status_code == (200 if allowed else 403)
    response = browser.post(reverse("cms-media-api"), {"file": photo()})
    assert response.status_code == (200 if allowed else 403)
    assert "no-cache" in response.headers["Cache-Control"]
    assert browser.get(reverse("cms-media-api")).status_code == (200 if allowed else 403)


@pytest.mark.django_db
def test_csrf_anonymous_limit_and_pagination(owner):
    browser, _ = owner
    assert Client().get(reverse("cms-media-api")).status_code == 403
    strict = Client(enforce_csrf_checks=True)
    strict.cookies = browser.cookies
    assert strict.post(reverse("cms-media-api"), {"file": photo()}).status_code == 403
    assert (
        browser.post(reverse("cms-media-api"), {"file": [photo() for _ in range(11)]}).status_code
        == 400
    )


@pytest.mark.django_db
def test_asset_version_and_required_alt(owner, django_capture_on_commit_callbacks):
    browser, user = owner
    asset = ready_asset(user, django_capture_on_commit_callbacks)
    url = reverse("cms-media-detail", args=[asset.pk])
    data = {"action": "save", "expected_version": asset.version, "alt_en": ""}
    with django_capture_on_commit_callbacks(execute=True):
        assert (
            browser.post(url, json.dumps(data), content_type="application/json").status_code == 200
        )
    asset.refresh_from_db()
    with pytest.raises(ValidationError, match="inglés"):
        media.reference(asset, "4:5")
    assert browser.post(url, json.dumps(data), content_type="application/json").status_code == 409
    assert browser.post(url, "{}", content_type="application/json").status_code == 409


@pytest.mark.django_db
def test_select_publish_restore_usage_and_frozen_versions(
    owner, django_capture_on_commit_callbacks
):
    browser, user = owner
    asset = ready_asset(user, django_capture_on_commit_callbacks)
    ref = media.reference(asset, "4:5")
    section = HomeSection(kind="story", title_es="Taller", title_en="Workshop")
    services.save_section(section, actor=user, expected_version=get_document("home").draft_version)
    data = {
        "action": "media-select",
        "id": str(section.pk),
        "slot": "image",
        "reference": ref,
        "expected_version": get_document("home").draft_version,
    }
    url = reverse("cms-editor-document")
    assert browser.post(url, json.dumps(data), content_type="application/json").status_code == 200
    assert browser.post(url, json.dumps(data), content_type="application/json").status_code == 409
    assert any(use["state"] == "Borrador" for use in media.used_by(asset, media.all_usage()))
    publication = services.publish_home(user, expected_version=get_document("home").draft_version)
    frozen = deepcopy(publication.snapshot)
    with pytest.raises(ValidationError, match="archivarla"):
        media.remove(asset, user)
    asset.alt_es = "Otro texto"
    asset.version += 1
    asset.save()
    render_media.apply(args=(asset.pk, asset.version)).get()
    assert media.resolve(ref, "es")["alt"] == "Foto de taller"
    asset.archived = True
    asset.save()
    services.restore_home(publication, user, expected_version=get_document("home").draft_version)
    assert publication.snapshot == frozen
    restored = next(
        row for row in selectors.home("es", preview=True)["sections"] if row["id"] == section.pk
    )
    published = next(row for row in frozen["es"] if row["id"] == section.pk)
    assert restored["image"] == published["image"]
    assert HomeSection.objects.get(pk=section.pk).image_reference == ref
    assert any(use["state"] == "Publicado" for use in media.used_by(asset, media.all_usage()))
    assert AuditLog.objects.filter(action="cms.media_selected").exists()


@pytest.mark.django_db
def test_cleanup_dry_real_and_only_cms_orphans(owner, django_capture_on_commit_callbacks, settings):
    _, user = owner
    from pathlib import Path

    root = Path(settings.MEDIA_ROOT)
    old = timezone.now() - timedelta(days=2)
    orphan = root / "cms/library/abandoned.webp"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(b"orphan")
    outside = root / "catalog/keep.webp"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_bytes(b"catalog")
    for file in (orphan, outside):
        os.utime(file, (old.timestamp(), old.timestamp()))
    link = root / "cms/library/link.webp"
    link.symlink_to(outside)
    asset = ready_asset(user, django_capture_on_commit_callbacks)
    asset.created_at = old
    asset.save(update_fields=["created_at"])
    section = HomeSection(kind="story", image_reference=media.reference(asset, "4:5"))
    services.save_section(section, actor=user, expected_version=get_document("home").draft_version)
    call_command("cleanup_cms_media", "--dry-run")
    assert orphan.exists()
    assert "cms/library/abandoned.webp" in collect(execute=True)
    assert not orphan.exists() and outside.exists() and link.is_symlink()
    assert MediaAsset.objects.filter(pk=asset.pk).exists()
    assert AuditLog.objects.filter(action="cms.media_file_deleted").exists()


@pytest.mark.django_db
def test_query_budget_independent_of_page_size(owner, django_assert_num_queries):
    browser, _ = owner
    # Auth/session + fixed usage scans + pagination. No query per image.
    MediaAsset.objects.bulk_create(
        [
            MediaAsset(
                original=f"cms/test-{i}.webp", sha256=hashlib.sha256(str(i).encode()).hexdigest()
            )
            for i in range(45)
        ]
    )
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as queries:
        response = browser.get(reverse("cms-media-api"))
    assert response.status_code == 200 and len(response.json()["items"]) == 40
    assert len(queries) <= 18
    assert len(browser.get(reverse("cms-media-api"), {"page": 2}).json()["items"]) == 5


@pytest.mark.django_db(transaction=True)
def test_migration_public_bytes_idempotent_safe_reverse():
    before = [("cms", "0018_registry_defaults")]
    after = [("cms", "0020_import_cms_media")]
    executor = MigrationExecutor(connection)
    try:
        executor.migrate(before)
        historical = executor.loader.project_state(before).apps
        Section = historical.get_model("cms", "HomeSection")
        seeded = Section.objects.create(
            kind="story",
            image="cms/legacy.webp",
            width=160,
            height=200,
            image_alt_es="Taller",
            image_alt_en="Workshop",
        )
        page, _ = historical.get_model("cms", "Page").objects.get_or_create(
            kind="personalize",
            defaults={"title_es": "Personaliza", "slug_es": "personaliza", "slug_en": "customize"},
        )
        snapshot = {
            lang: {"slug": "personaliza", "title": "Personaliza", "body_html": ""}
            for lang in ("es", "en")
        }
        historical.get_model("cms", "PageRevision").objects.create(
            page=page, version=page.version + 1, snapshot=snapshot
        )
        page.status = "published"
        page.version += 1
        page.save()
        historical.get_model("cms", "HomePublication").objects.create(
            snapshot={
                lang: [
                    {
                        "id": seeded.pk,
                        "kind": "story",
                        "schema_version": 1,
                        "title": "Taller",
                        "body": "",
                        "cta": None,
                        "image": {
                            "src": "/media/cms/legacy.webp",
                            "srcset": "",
                            "width": 160,
                            "height": 200,
                            "alt": "Taller" if lang == "es" else "Workshop",
                        },
                    }
                ]
                for lang in ("es", "en")
            }
        )
        urls = [reverse("cms-home"), reverse("cms-page-kind", args=["personalize"])]
        baseline = {
            (url, lang): historical_public_bytes(historical, url, lang)
            for url in urls
            for lang in ("es", "en")
        }
        executor = MigrationExecutor(connection)
        executor.migrate(after)
        current = executor.loader.project_state(after).apps
        Asset = current.get_model("cms", "MediaAsset")
        module = import_module("apps.cms.migrations.0020_import_cms_media")
        with connection.schema_editor() as editor:
            module.migrate_media(current, editor)
            count = Asset.objects.count()
            module.migrate_media(current, editor)
            assert Asset.objects.count() == count
        for url in urls:
            for lang in ("es", "en"):
                assert historical_public_bytes(current, url, lang) == baseline[url, lang]
        for lang in ("es", "en"):
            row = current.get_model("cms", "HomeSection").objects.get(pk=seeded.pk)
            expected = {
                "src": "/media/cms/legacy.webp",
                "srcset": "",
                "width": 160,
                "height": 200,
                "alt": "Taller" if lang == "es" else "Workshop",
            }
            assert selectors.image_data(row, lang) == expected
        executor.migrate(before)
        assert Section.objects.filter(image="cms/legacy.webp").exists()
    finally:
        latest = MigrationExecutor(connection)
        latest.migrate(latest.loader.graph.leaf_nodes())


@pytest.mark.django_db
def test_failed_worker_retry_and_archiving_conflict(owner, django_capture_on_commit_callbacks):
    browser, user = owner
    with django_capture_on_commit_callbacks(execute=True):
        asset, _ = media.upload(photo(), user)
    asset.refresh_from_db()
    # A current generation failure sets a clear state and is retried by Celery.
    asset.version += 1
    asset.save()
    with (
        patch("apps.cms.media.validated_image", side_effect=OSError("private/server/path")),
        pytest.raises((OSError, Retry)),
    ):
        render_media.apply(args=(asset.pk, asset.version)).get()
    asset.refresh_from_db()
    assert asset.state == "failed"
    url = reverse("cms-media-detail", args=[asset.pk])
    with django_capture_on_commit_callbacks(execute=True):
        response = browser.post(
            url,
            json.dumps({"action": "retry", "expected_version": asset.version}),
            content_type="application/json",
        )
    assert response.status_code == 200 and "private/server/path" not in response.content.decode()
    asset.refresh_from_db()
    assert asset.state == "ready"
    version = asset.version
    data = json.dumps({"action": "archive", "expected_version": version})
    assert browser.post(url, data, content_type="application/json").status_code == 200
    assert browser.post(url, data, content_type="application/json").status_code == 409


@pytest.mark.django_db
def test_history_only_photo_retained_and_abandoned_upload_removed(
    owner, django_capture_on_commit_callbacks
):
    _, user = owner
    asset = ready_asset(user, django_capture_on_commit_callbacks)
    section = HomeSection(kind="story", image_reference=media.reference(asset, "4:5"))
    services.save_section(section, actor=user, expected_version=get_document("home").draft_version)
    old = services.publish_home(user, expected_version=get_document("home").draft_version)
    section_id = section.pk
    section.delete()
    services.publish_home(user, expected_version=get_document("home").draft_version)
    uses = media.used_by(asset, media.all_usage())
    assert any(use["state"] == "Historial" for use in uses)
    with pytest.raises(ValidationError):
        media.remove(asset, user)
    services.restore_home(old, user, expected_version=get_document("home").draft_version)
    assert (
        selectors.image_data(HomeSection.objects.get(pk=section_id), "es")["src"]
        == media.resolve(media.reference(asset, "4:5"), "es")["src"]
    )
    with django_capture_on_commit_callbacks(execute=True):
        abandoned, _ = media.upload(photo(size=(64, 64)), user)
    MediaAsset.objects.filter(pk=abandoned.pk).update(created_at=timezone.now() - timedelta(days=2))
    collect(execute=False)
    assert MediaAsset.objects.filter(pk=abandoned.pk).exists()
    collect(execute=True)
    assert not MediaAsset.objects.filter(pk=abandoned.pk).exists()
    assert AuditLog.objects.filter(action="cms.media_orphan_removed").exists()


def test_library_routes_anonymous_and_no_cache():
    for name, args in (("cms-media", []), ("cms-media-api", []), ("cms-media-detail", [1])):
        response = Client().get(reverse(name, args=args))
        assert response.status_code == 403
        assert "no-store" in response.headers["Cache-Control"]


def test_reference_contract_and_archived_restore_without_db():
    from types import SimpleNamespace

    asset = SimpleNamespace(
        archived=False, versions={"2": {"4:5": {"alt": {"es": "Taller", "en": "Workshop"}}}}
    )
    ref = {"asset": 1, "crop": "4:5", "version": 2}
    with patch("apps.cms.media.MediaAsset.objects") as rows:
        rows.filter.return_value.first.return_value = asset
        assert media.validate_reference(ref) == ref
        asset.archived = True
        assert media.validate_reference(ref) == ref
        with pytest.raises(ValidationError, match="archivada"):
            media.validate_reference(ref, selecting=True)
        asset.archived = False
        asset.versions["2"]["4:5"]["alt"]["en"] = ""
        with pytest.raises(ValidationError, match="inglés"):
            media.validate_reference(ref)
    for bad in (
        {"asset": 1},
        {**ref, "asset": True},
        {**ref, "version": "2"},
        {**ref, "crop": "2:3"},
    ):
        with pytest.raises(ValidationError):
            media.validate_reference(bad)


@pytest.mark.django_db
def test_compatibility_upload_keeps_uncropped_original_and_alt_versions(owner):
    _, user = owner
    section = HomeSection(
        kind="story", image=photo(size=(480, 200)), image_alt_es="Antes", image_alt_en="Before"
    )
    services.save_section(section, actor=user, expected_version=get_document("home").draft_version)
    asset = MediaAsset.objects.get(pk=section.image_reference["asset"])
    with asset.original.open("rb") as file:
        assert Image.open(file).size == (480, 200)
    assert (section.width, section.height) == (160, 200)
    old_ref = deepcopy(section.image_reference)
    section.image_alt_es = "Después"
    services.save_section(section, actor=user, expected_version=get_document("home").draft_version)
    assert media.resolve(old_ref, "es")["alt"] == "Antes"
    assert selectors.image_data(section, "es")["alt"] == "Después"


def test_usage_index_matches_references_paths_and_historical_srcsets():
    asset = MediaAsset(
        pk=37,
        original="cms/library/original.webp",
        versions={"0": {"4:5": {"srcset": "/media/cms/old.webp 480w"}}},
    )
    sources = media.UsageIndex(
        [
            ("Borrador", "Inicio", {"image_reference": {"asset": 37, "version": 1}}),
            ("Publicado", "Inicio", {"image": "cms/library/original.webp"}),
            (
                "Historial",
                "Inicio 1",
                {"srcset": "/media/cms/old.webp 480w, /media/cms/large.webp 960w"},
            ),
            ("Historial", "Otra foto", {"src": "/media/cms/old.webp-other"}),
        ]
    )
    assert media.used_by(asset, sources) == [
        {"state": "Borrador", "label": "Inicio"},
        {"state": "Publicado", "label": "Inicio"},
        {"state": "Historial", "label": "Inicio 1"},
    ]
    assert media.used_by(MediaAsset(pk=38, original="cms/unused.webp"), sources) == []
