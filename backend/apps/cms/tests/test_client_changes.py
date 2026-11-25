import pytest

from apps.catalog.models import Category, Piece
from apps.cms import selectors, services
from apps.cms.api.serializers import SiteSettingsSerializer
from apps.cms.models import HomeSection
from apps.cms.tests.helpers import cms_version
from apps.core.selectors import get_solo

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("scale", [90, 100, 110, 120])
def test_settings_serializer_numeric_scales(scale):
    config = get_solo()
    config.title_scale = scale
    config.text_scale = scale
    config.save()
    data = SiteSettingsSerializer(selectors.site_settings("es")).data
    assert data["title_scale"] == scale / 100
    assert data["text_scale"] == scale / 100
    assert isinstance(data["title_scale"], float)


def test_category_grid_live_counts_and_localization(cms_actor):
    Category.objects.all().delete()
    root = Category.objects.create(
        name_es="Anillos", name_en="Rings", slug_es="anillos", slug_en="rings"
    )
    child = Category.objects.create(name_es="Compromiso", slug_es="compromiso", parent=root)
    Category.objects.create(name_es="Oculta", slug_es="oculta", is_active=False)
    for index, (category, status) in enumerate(
        [(root, "published"), (child, "published"), (root, "draft")]
    ):
        Piece.objects.create(
            sku=f"GRID-{index}",
            name_es="Pieza",
            slug_es=f"grid-{index}",
            category=category,
            status=status,
            price_cents=100,
        )
    section = HomeSection(
        kind="category_grid", title_es="Comprar por categoría", title_en="Shop by category"
    )
    services.save_section(section, expected_version=cms_version(section), actor=cms_actor)
    rendered = selectors.render_sections([section], "en")
    assert rendered[0]["title"] == "Shop by category"
    assert rendered[0]["subtitle"] == ""
    data = selectors.resolve_live(rendered, "en")[0]["categories"]
    assert data == [
        {"name": "Rings", "slug": "rings", "href": "/en/jewelry/rings", "count": 2, "image": None}
    ]


def test_category_conversion_preserves_publication_until_publish():
    from importlib import import_module

    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    from apps.cms.models import HomePublication

    snapshot = {"es": [{"id": 99, "kind": "story", "title": "Nuestra historia"}], "en": []}
    publication = HomePublication.objects.create(snapshot=snapshot)
    story = HomeSection.objects.create(
        kind="story", title_es="Nuestra historia", title_en="Our story"
    )
    apps = MigrationExecutor(connection).loader.project_state().apps
    migration = import_module("apps.cms.migrations.0011_home_category_grid")
    migration.replace_story(apps, None)
    story.refresh_from_db()
    publication.refresh_from_db()
    assert story.kind == "category_grid"
    assert story.title_es == "Comprar por categoría"
    assert story.title_en == "Shop by category"
    assert publication.snapshot == snapshot
    assert [
        {key: value for key, value in section.items() if key != "schema_version"}
        for section in selectors.home("es")["sections"]
    ] == snapshot["es"]


def test_business_settings_contract_in_both_languages():
    config = get_solo()
    config.business_locality = "Armenia"
    config.seo_home_title_en = "Custom English title"
    config.save()
    es = SiteSettingsSerializer(selectors.site_settings("es")).data
    en = SiteSettingsSerializer(selectors.site_settings("en")).data
    assert es["business_locality"] == en["business_locality"] == "Armenia"
    assert es["appointment_only"] is True
    assert en["seo_home_title"] == "Custom English title"
    assert "streetAddress" not in es
