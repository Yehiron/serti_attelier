from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from django.db import connection, migrations
from django.db.migrations.executor import MigrationExecutor

from apps.cms import selectors
from apps.cms.models import HomeSection


@pytest.mark.django_db(transaction=True)
def test_paired_slides_split_without_storage_changes() -> None:
    before = ("cms", "0006_heroslide")
    after = ("cms", "0009_remove_heroslide_mobile_fields")
    executor = MigrationExecutor(connection)
    # Only test setup bypasses the irreversible data guard to build the old schema.
    migration = executor.loader.disk_migrations[("cms", "0008_split_hero_slides")]
    for operation in migration.operations:
        if isinstance(operation, migrations.RunPython):
            operation.reverse_code = migrations.RunPython.noop
    executor.migrate([before])
    try:
        apps = executor.loader.project_state([before]).apps
        section = apps.get_model("cms", "HomeSection").objects.create(kind="hero")
        slides = apps.get_model("cms", "HeroSlide").objects
        paired = slides.create(
            section=section,
            position=3,
            image="desktop.webp",
            width=1920,
            height=900,
            renditions={"webp": {"960": "desktop-960.webp"}},
            image_mobile="mobile.webp",
            mobile_width=1080,
            mobile_height=1350,
            mobile_renditions={"webp": {"960": "mobile-960.webp"}},
            alt_es="Foto",
            alt_en="Photo",
        )
        slides.create(
            section=section,
            position=0,
            image_mobile="phone-only.webp",
            mobile_width=750,
            mobile_height=1000,
            alt_es="Celular",
            alt_en="Phone",
        )
        slides.create(
            section=section,
            position=4,
            image="desktop-only.webp",
            width=1000,
            height=500,
            alt_es="Computador",
            alt_en="Desktop",
        )
        with (
            patch("django.core.files.storage.default_storage.save") as save,
            patch("django.core.files.storage.default_storage.delete") as delete,
        ):
            executor = MigrationExecutor(connection)
            executor.migrate([after])
        save.assert_not_called()
        delete.assert_not_called()
        new_apps = executor.loader.project_state([after]).apps
        new_slides = new_apps.get_model("cms", "HeroSlide").objects
        assert new_slides.count() == 4
        desktop = new_slides.get(pk=paired.pk)
        mobile = new_slides.get(image="mobile.webp")
        assert desktop.device == "desktop"
        assert desktop.image.name == "desktop.webp"
        assert desktop.renditions == {"webp": {"960": "desktop-960.webp"}}
        assert (mobile.width, mobile.height, mobile.position) == (1080, 1350, 3)
        assert mobile.renditions == {"webp": {"960": "mobile-960.webp"}}
        assert (mobile.alt_es, mobile.alt_en) == ("Foto", "Photo")
        # Runtime readers include fields added by later migrations. Finish the
        # expansion before using them; split assertions above use historical apps.
        latest = MigrationExecutor(connection)
        latest.migrate(latest.loader.graph.leaf_nodes())
        payload: Any = selectors.render_sections([HomeSection.objects.get(pk=section.pk)], "es")[0]
        assert [bool(row["image"]) for row in payload["slides"]] == [True, True, False, False]
        assert [bool(row["mobile_image"]) for row in payload["slides"]] == [
            False,
            False,
            True,
            True,
        ]
        assert payload["image"] == payload["slides"][0]["image"]
    finally:
        # Return to the latest schema, not just `after`: later migrations add columns
        # that transactional tests running afterwards rely on.
        latest = MigrationExecutor(connection)
        latest.migrate(latest.loader.graph.leaf_nodes())
