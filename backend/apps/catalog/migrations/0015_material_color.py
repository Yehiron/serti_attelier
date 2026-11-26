import unicodedata

from django.core.validators import RegexValidator
from django.db import migrations, models


def populate(apps, schema_editor):
    Material = apps.get_model("catalog", "Material")
    for material in Material.objects.using(schema_editor.connection.alias).all():
        name = " ".join(unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().lower() for value in (material.name_es, material.name_en))
        for words, color in ((('blanco', 'white'), '#dcdcd8'), (('plata', 'silver'), '#c9ccce'), (('rosa', 'rose', 'pink'), '#e3a98e'), (('oro', 'gold', 'amarillo', 'yellow'), '#d9b25f')):
            if any(word in name for word in words):
                material.color = color
                material.save(update_fields=['color'])
                break


class Migration(migrations.Migration):
    dependencies = [('catalog', '0014_stone_color')]
    operations = [
        migrations.AddField(model_name='material', name='color', field=models.CharField(blank=True, max_length=7, validators=[RegexValidator(r'^#[0-9a-fA-F]{6}$')], verbose_name='Tono del metal', help_text='Se usa en Personaliza y en la ficha de las piezas')),
        migrations.RunPython(populate, migrations.RunPython.noop),
    ]
