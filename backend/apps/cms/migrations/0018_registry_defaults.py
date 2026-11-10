"""Expansión sin traslados: 0017 ya asigna 1 y {} a todas las filas antiguas.

La normalización puede repetirse. No toca publicaciones ni contenido editorial.
La reversa de datos conserva valores utilizados; revertir 0017 requiere exportar
antes props si se han creado secciones nuevas.
"""
from django.db import migrations


def normalize(apps, schema_editor):
    section = apps.get_model('cms', 'HomeSection')
    rows = section.objects.using(schema_editor.connection.alias)
    rows.filter(schema_version__isnull=True).update(schema_version=1)
    rows.filter(props__isnull=True).update(props={})


class Migration(migrations.Migration):
    dependencies = [('cms', '0017_homesection_props_homesection_schema_version_and_more')]
    operations = [migrations.RunPython(normalize, migrations.RunPython.noop)]
