from django.db import migrations

FIELDS = ("name_es", "name_en", "sku", "short_description_es", "short_description_en")


def create_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("""
        CREATE FUNCTION catalog_immutable_unaccent(text) RETURNS text
        LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
        AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$
    """)
    for field in FIELDS:
        schema_editor.execute(
            f"CREATE INDEX catalog_trgm_{field}_idx ON catalog_piece "
            f"USING gin (catalog_immutable_unaccent(lower({field})) gin_trgm_ops)"
        )


def drop_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for field in FIELDS:
        schema_editor.execute(f"DROP INDEX catalog_trgm_{field}_idx")
    schema_editor.execute("DROP FUNCTION catalog_immutable_unaccent(text)")


class Migration(migrations.Migration):
    dependencies = [("catalog", "0011_piece_piece_public_order_idx")]
    operations = [migrations.RunPython(create_indexes, drop_indexes)]
