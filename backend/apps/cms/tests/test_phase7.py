"""Identity invariants; database cases must run on PostgreSQL."""

import json
from copy import deepcopy
from importlib import import_module
from types import SimpleNamespace

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.db.migrations.exceptions import IrreversibleError
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse

from apps.accounts.roles import CONTENIDO, OPERACIONES, PROPIETARIO
from apps.cms import brand, visual_documents
from apps.cms.documents import ContentConflict, edit_document, get_document
from apps.cms.models import BrandPublication, DraftRevision
from apps.cms.publishing import pending_changes
from apps.core.admin import SiteSettingsForm
from apps.core.models import SiteSettings
from apps.core.tests.test_dashboard_client import staff


@pytest.fixture(autouse=True)
def identity_for_database_case(request):
    if not request.node.get_closest_marker("django_db") or "migration" in request.node.name:
        return
    request.getfixturevalue("db")
    doc = get_document(brand.KEY)
    if not doc.brand_identity:
        publication = BrandPublication.objects.create(snapshot=deepcopy(brand.DEFAULT))
        doc.brand_identity = deepcopy(brand.DEFAULT)
        doc.brand_publication = publication
        doc.published_version = doc.draft_version
        doc.save()


def test_reference_contrast_and_defaults():
    assert brand.luminance("#000000") == 0
    assert brand.luminance("#ffffff") == 1
    assert brand.contrast("#000000", "#ffffff") == 21
    assert brand.contrast("#777777", "#ffffff") == pytest.approx(4.478, abs=0.001)
    assert all(check["ok"] for check in brand.checks(brand.DEFAULT))
    assert brand.validate(brand.DEFAULT, publishing=True) == brand.DEFAULT
    assert import_module("apps.cms.migrations.0026_initial_brand").ORIGINAL == brand.DEFAULT
    assert brand.groups(brand.DEFAULT, deepcopy(brand.DEFAULT)) == []


@pytest.mark.parametrize(
    "key,value",
    [
        ("wine", "red"),
        ("cream", "#fff"),
        ("ink", "#000000; color:red"),
        ("paper", "#12345678"),
        ("title_font", "arial"),
        ("text_font", "ninna"),
        ("title_scale", 101),
        ("text_scale", "100"),
        ("wine", "#ffffff"),
        ("cream", "#333333"),
    ],
)
def test_closed_fields(key, value):
    with pytest.raises(ValidationError):
        brand.validate({**brand.DEFAULT, key: value})


def test_draft_can_warn_but_publication_blocked():
    value = {**brand.DEFAULT, "crimson": "#ffffff"}
    assert brand.validate(value) == value
    assert any(not row["ok"] and row["required"] for row in brand.checks(value))
    with pytest.raises(ValidationError, match="contraste"):
        brand.validate(value, publishing=True)
    assert "title_scale" not in SiteSettingsForm.base_fields
    assert "text_scale" not in SiteSettingsForm.base_fields
    assert "whatsapp_number" in SiteSettingsForm.base_fields


@pytest.mark.parametrize(
    "key,value", [("wine", "#6a1f36"), ("title_font", "cormorant"), ("title_scale", 110)]
)
def test_readable_changes(key, value):
    groups = brand.groups({**brand.DEFAULT, key: value}, brand.DEFAULT)
    assert len(groups) == 1 and len(groups[0]["rows"]) == 1
    assert groups[0]["rows"][0]["label"] == brand.LABELS[key]


@pytest.mark.django_db
def test_full_versioned_identity_lifecycle():
    _client, owner = staff(PROPIETARIO)
    doc = get_document(brand.KEY)
    original = doc.brand_publication
    assert pending_changes(brand.KEY)["count"] == 0
    before = BrandPublication.objects.count()
    assert brand.publish(owner, expected_version=doc.draft_version).pk == original.pk
    assert BrandPublication.objects.count() == before
    with edit_document(brand.KEY, owner, doc.draft_version):
        visual_documents.mutate(
            brand.KEY, "update", {"id": "brand", "values": {"wine": "#6a1f36"}}, owner, None
        )
    with pytest.raises(ContentConflict):
        brand.publish(owner, expected_version=doc.draft_version)
    doc.refresh_from_db()
    assert pending_changes(brand.KEY)["count"] == 1
    published = brand.publish(owner, expected_version=doc.draft_version)
    assert published.snapshot["wine"] == "#6a1f36"
    assert pending_changes(brand.KEY)["count"] == 0
    brand.restore(original, owner, expected_version=doc.draft_version)
    assert DraftRevision.objects.get(document=doc).restored_from_brand_id == original.pk
    assert brand.public_identity()["wine"] == "#6a1f36"
    assert brand.public_identity(preview=True)["wine"] == original.snapshot["wine"]
    doc.refresh_from_db()
    brand.publish(owner, expected_version=doc.draft_version)
    assert pending_changes(brand.KEY)["count"] == 0
    # Identity never adds fields to other document comparisons.
    assert all(pending_changes(key)["count"] == 0 for key in ("menu:main", "menu:footer"))


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role,edit,publish",
    [(CONTENIDO, True, False), (OPERACIONES, False, False), (PROPIETARIO, True, True)],
)
def test_roles_and_http_versions(role, edit, publish):
    client, actor = staff(role)
    url = reverse("cms-editor-document") + "?document=" + brand.KEY
    response = client.get(url)
    assert response.status_code == (200 if edit else 403)
    if not edit:
        assert client.post(url, data="{}", content_type="application/json").status_code == 403
        return
    state = response.json()
    payload = {
        "action": "update",
        "id": "brand",
        "values": {"crimson": "#ffffff"},
        "expected_version": state["version"],
    }
    saved = client.post(url, data=json.dumps(payload), content_type="application/json")
    assert saved.status_code == 200
    assert any(not check["ok"] for check in saved.json()["brand_checks"])
    assert (
        client.post(url, data=json.dumps(payload), content_type="application/json").status_code
        == 409
    )
    from urllib.parse import parse_qs, urlsplit

    token = parse_qs(urlsplit(saved.json()["preview"]["es"]).query)["token"][0]
    assert client.get(reverse("cms-brand"), {"preview": token}).status_code == 200
    doc = get_document(brand.KEY)
    review = reverse("cms-review-publish", args=[brand.KEY])
    assert client.post(review, {"expected_version": doc.draft_version}).status_code == (
        400 if publish else 403
    )
    if not publish:
        with pytest.raises(PermissionDenied):
            brand.restore(doc.brand_publication, actor, expected_version=doc.draft_version)
        with pytest.raises(PermissionDenied):
            brand.publish(actor, expected_version=doc.draft_version)


@pytest.mark.django_db
def test_public_contract_preview_and_query_budget(django_assert_num_queries):
    from django.test import Client

    from apps.cms.api.serializers import BrandSerializer

    with django_assert_num_queries(1):
        data = brand.public_identity()
    serializer = BrandSerializer(data=data)
    assert serializer.is_valid(), serializer.errors
    with django_assert_num_queries(1):
        response = Client().get(reverse("cms-brand"))
    assert response.status_code == 200 and response.json() == data
    assert Client().get(reverse("cms-brand"), {"preview": "bad"}).status_code == 403
    # Legacy API retains numeric scale behavior; storefront reads only the identity.
    config = SiteSettings.objects.first() or SiteSettings.objects.create()
    config.title_scale = 120
    config.save()
    assert brand.public_identity()["title_scale"] == data["title_scale"]


@pytest.mark.django_db(transaction=True)
def test_initial_migration_copies_scales_idempotently_and_reverses():
    before = [("cms", "0025_brandpublication_and_more")]
    after = [("cms", "0026_initial_brand")]
    executor = MigrationExecutor(connection)
    # Remove the intact test seed before rolling back data migration.
    try:
        executor.migrate(before)
        # 0025 does not depend on core; include it so SiteSettings exists in the state.
        historical = executor.loader.project_state(
            [*before, ("core", "0008_sitesettings_text_scale_sitesettings_title_scale")]
        ).apps
        Settings = historical.get_model("core", "SiteSettings")
        config = Settings.objects.first() or Settings.objects.create()
        config.title_scale = 110
        config.text_scale = 90
        config.save()
        executor = MigrationExecutor(connection)
        executor.migrate(after)
        apps = executor.loader.project_state(after).apps
        Document = apps.get_model("cms", "ContentDocument")
        Publication = apps.get_model("cms", "BrandPublication")
        doc = Document.objects.get(key=brand.KEY)
        seed = import_module("apps.cms.migrations.0026_initial_brand")
        expected = {**seed.ORIGINAL, "title_scale": 110, "text_scale": 90}
        assert doc.brand_identity == expected
        assert Publication.objects.get(pk=doc.brand_publication_id).snapshot == expected
        schema = SimpleNamespace(connection=connection)
        seed.seed(apps, schema)
        assert Publication.objects.count() == 1
        doc.brand_identity = {**expected, "wine": "#6a1f36"}
        doc.save()
        with pytest.raises(IrreversibleError):
            seed.reverse_seed(apps, schema)
        doc.brand_identity = expected
        doc.save()
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        assert not Document.objects.filter(key=brand.KEY).exists()
    finally:
        latest = MigrationExecutor(connection)
        latest.migrate(latest.loader.graph.leaf_nodes())


@pytest.mark.django_db
@pytest.mark.parametrize(
    "slot,size,transparent,accepted",
    [
        ("logo_light", (320, 103), True, True),
        ("logo_dark", (320, 103), False, False),
        ("monogram_light", (96, 24), True, True),
        ("logo_light", (80, 20), True, False),
        ("icon", (512, 512), False, True),
        ("icon", (512, 600), True, False),
        ("icon", (256, 256), True, False),
    ],
)
def test_logo_validation_and_icon_renditions(
    tmp_path, settings, slot, size, transparent, accepted, django_assert_num_queries
):
    from io import BytesIO
    from unittest.mock import patch

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    from apps.cms import media
    from apps.cms.models import MediaAsset

    settings.MEDIA_ROOT = tmp_path
    _, owner = staff(PROPIETARIO)
    image = Image.new(
        "RGBA" if transparent else "RGB", size, (100, 20, 40, 0) if transparent else (100, 20, 40)
    )
    if transparent:
        image.putpixel((0, 0), (100, 20, 40, 255))
    output = BytesIO()
    image.save(output, format="PNG")
    with patch("apps.cms.media.enqueue"):
        asset, _ = media.upload(
            SimpleUploadedFile("logo.png", output.getvalue(), content_type="image/png"), owner
        )
    asset.alt_es = "Marca"
    asset.alt_en = "Brand"
    asset.save()
    media.render(asset.pk, asset.version)
    asset.refresh_from_db()
    ref = {"asset": asset.pk, "crop": "1:1", "version": asset.version}
    if not accepted:
        with pytest.raises(ValidationError):
            brand.validate_logo(slot, ref)
        return
    assert brand.validate_logo(slot, ref) == ref
    if slot == "icon":
        paths = asset.versions[str(asset.version)]["brand_icons"]
        assert set(paths) == {"32", "180", "192", "512", "ico"}
        for n in (32, 180, 192, 512):
            with (
                media.default_storage.open(paths[str(n)], "rb") as source,
                Image.open(source) as rendered,
            ):
                assert rendered.size == (n, n) and rendered.format == "PNG"
        with (
            media.default_storage.open(paths["ico"], "rb") as source,
            Image.open(source) as rendered,
        ):
            assert rendered.format == "ICO"
    doc = get_document(brand.KEY)
    with edit_document(brand.KEY, owner, doc.draft_version):
        visual_documents.mutate(
            brand.KEY, "media-select", {"id": "brand", "slot": slot, "reference": ref}, owner, None
        )
    usage = media.used_by(asset, media.all_usage())
    assert any(brand.SLOTS[slot] in row["label"] for row in usage)
    with pytest.raises(ValidationError):
        media.remove(asset, owner)
    doc.refresh_from_db()
    publication = brand.publish(owner, expected_version=doc.draft_version)
    assert publication.snapshot[slot] == ref
    with django_assert_num_queries(2):
        data = brand.public_identity()
    assert data[slot]
    assert MediaAsset.objects.filter(pk=asset.pk).exists()


@pytest.mark.django_db
def test_svg_is_rejected_in_library(tmp_path, settings):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.cms import media

    settings.MEDIA_ROOT = tmp_path
    _, owner = staff(PROPIETARIO)
    with pytest.raises(ValidationError, match="SVG"):
        media.upload(
            SimpleUploadedFile(
                "logo.svg", b"<svg><script>alert(1)</script></svg>", content_type="image/svg+xml"
            ),
            owner,
        )


def test_contrast_messages_match_results_and_spanish_numbers():
    value = {**brand.DEFAULT, "ink": "#9a8a8a"}
    row = brand.checks(value)[0]
    assert not row["ok"]
    assert row["message"] == (
        "✗ El texto sobre el fondo no se lee bien (2,40:1; mínimo 4,5:1). "
        "Oscurece el texto o aclara el fondo."
    )
    for cream in ("#ead9cb", "#0b6e4f"):
        heart = brand.checks({**brand.DEFAULT, "cream": cream})[-1]
        assert ("no se distingue" in heart["message"]) is not heart["ok"]
        assert "mínimo 3:1" in heart["message"]
        assert heart["message"].startswith("✓" if heart["ok"] else "✗")


def test_brand_review_color_samples_and_slot_names():
    current = {**brand.DEFAULT, "wine": "#6a1f36"}
    row = brand.groups(current, brand.DEFAULT)[0]["rows"][0]
    assert row["before_color"] == brand.DEFAULT["wine"]
    assert row["after_color"] == "#6a1f36"
    previous = {**brand.DEFAULT, "sharing": {"asset": 1}, "icon": {"asset": 2}}
    rows = brand.groups(brand.DEFAULT, previous)[0]["rows"]
    assert any(row["after"] == "Sin imagen (se usa la de cada página)" for row in rows)
    assert any(row["after"] == "Ícono original" for row in rows)


@pytest.mark.django_db
def test_brand_review_blocks_bad_contrast_on_get():
    client, _ = staff(PROPIETARIO)
    doc = get_document(brand.KEY)
    doc.brand_identity = {**doc.brand_identity, "ink": "#9a8a8a"}
    doc.draft_version += 1
    doc.save()
    url = reverse("cms-review-publish", args=[brand.KEY])
    response = client.get(url)
    assert response.status_code == 200
    html = response.content.decode()
    assert "no se lee bien (2,40:1; mínimo 4,5:1)" in html
    assert 'disabled aria-disabled="true"' in html
    assert "Revisa los textos en español e inglés" not in html
    assert "cms-color-swatch" in html
    assert client.post(url, {"expected_version": doc.draft_version}).status_code == 400
