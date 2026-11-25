from django.db import migrations

TABLES = ("category", "stone", "material", "collection")
FIELDS = ("name_es", "name_en")


def create_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        for field in FIELDS:
            schema_editor.execute(
                f"CREATE INDEX catalog_{table}_{field}_trgm_idx ON catalog_{table} "
                f"USING gin (upper(catalog_immutable_unaccent({field})) gin_trgm_ops)"
            )


def drop_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        for field in FIELDS:
            schema_editor.execute(f"DROP INDEX catalog_{table}_{field}_trgm_idx")


class Migration(migrations.Migration):
    dependencies = [("catalog", "0012_search_trigram_indexes")]
    operations = [migrations.RunPython(create_indexes, drop_indexes)]
