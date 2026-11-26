import unicodedata

from django.core.validators import RegexValidator
from django.db import migrations, models

COLORS = {"esmeralda": "#1f7a55", "rubi": "#a51c3a", "zafiro": "#244a9c", "diamante": "#e9eef2"}


def populate(apps, schema_editor):
    Stone = apps.get_model("catalog", "Stone")
    for stone in Stone.objects.using(schema_editor.connection.alias).all():
        for value in (stone.name_es, stone.slug_es):
            key = (
                unicodedata.normalize("NFKD", value or "")
                .encode("ascii", "ignore")
                .decode()
                .lower()
            )
            if key in COLORS:
                stone.color = COLORS[key]
                stone.save(update_fields=["color"])
                break


def clear(apps, schema_editor):
    apps.get_model("catalog", "Stone").objects.using(schema_editor.connection.alias).filter(
        color__in=COLORS.values()
    ).update(color="")


class Migration(migrations.Migration):
    dependencies = [("catalog", "0013_taxonomy_search_trigram_indexes")]
    operations = [
        migrations.AddField(
            model_name="stone",
            name="color",
            field=models.CharField(
                blank=True,
                help_text="Se usa en Personaliza y en la ficha de las piezas",
                max_length=7,
                validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$")],
                verbose_name="Color de la gema",
            ),
        ),
        migrations.RunPython(populate, clear),
    ]
