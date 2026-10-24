import csv
from pathlib import Path

from django.db import migrations


def load_divipola(apps, schema_editor):
    Department = apps.get_model('core', 'Department')
    Municipality = apps.get_model('core', 'Municipality')
    alias = schema_editor.connection.alias
    departments = {}
    municipalities = []
    path = Path(__file__).resolve().parents[1] / 'data' / 'divipola.csv'
    with path.open(encoding='utf-8-sig', newline='') as source:
        for row in csv.DictReader(source):
            code = row['department_code']
            departments[code] = Department(code=code, name=row['department_name'])
            municipalities.append(Municipality(code=row['municipality_code'], name=row['municipality_name'], department_id=code, kind=row['kind']))
    Department.objects.using(alias).bulk_create(departments.values())
    Municipality.objects.using(alias).bulk_create(municipalities)


def unload_divipola(apps, schema_editor):
    apps.get_model('core', 'Municipality').objects.using(schema_editor.connection.alias).all().delete()
    apps.get_model('core', 'Department').objects.using(schema_editor.connection.alias).all().delete()


class Migration(migrations.Migration):
    dependencies = [('core', '0001_initial')]
    operations = [migrations.RunPython(load_divipola, unload_divipola)]
