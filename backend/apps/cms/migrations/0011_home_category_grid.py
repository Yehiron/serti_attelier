from django.db import migrations


def replace_story(apps, schema_editor):
    # Draft only: published immutable snapshots change on the next explicit publication.
    HomeSection = apps.get_model('cms', 'HomeSection')
    HomeSection.objects.filter(kind='story').update(
        kind='category_grid', title='Comprar por categoría',
        title_es='Comprar por categoría', title_en='Shop by category', cta_kind='none',
    )


class Migration(migrations.Migration):
    dependencies = [('cms', '0010_alter_homesection_kind')]
    # Keep content conversion separate from PostgreSQL schema alterations.
    operations = [migrations.RunPython(replace_story, migrations.RunPython.noop)]
