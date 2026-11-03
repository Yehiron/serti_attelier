# Split paired slides into one row per device. Kept apart from the schema changes:
# PostgreSQL cannot ALTER a table with pending deferred trigger events in one transaction.

from __future__ import annotations

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor


def split_slides(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    slides = apps.get_model("cms", "HeroSlide").objects.using(schema_editor.connection.alias)
    for slide in list(slides.all()):
        if not slide.image_mobile:
            continue
        mobile = {
            "image": slide.image_mobile.name,
            "renditions": slide.mobile_renditions,
            "width": slide.mobile_width,
            "height": slide.mobile_height,
            "device": "mobile",
        }
        if slide.image:
            slides.create(section_id=slide.section_id, position=slide.position, alt=slide.alt,
                          alt_es=slide.alt_es, alt_en=slide.alt_en, **mobile)
        else:
            slides.filter(pk=slide.pk).update(**mobile)


def irreversible(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    from django.db.migrations.exceptions import IrreversibleError

    raise IrreversibleError("Independent device slides cannot be paired automatically.")


class Migration(migrations.Migration):

    dependencies = [
        ('cms', '0007_heroslide_device'),
    ]

    operations = [
        migrations.RunPython(split_slides, irreversible),
    ]
