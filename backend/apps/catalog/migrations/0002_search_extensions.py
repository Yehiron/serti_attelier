from django.contrib.postgres.operations import TrigramExtension, UnaccentExtension
from django.db import migrations


class VendorSafeUnaccentExtension(UnaccentExtension):
    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor == 'postgresql':
            super().database_backwards(app_label, schema_editor, from_state, to_state)


class VendorSafeTrigramExtension(TrigramExtension):
    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor == 'postgresql':
            super().database_backwards(app_label, schema_editor, from_state, to_state)


class Migration(migrations.Migration):
    dependencies = [('catalog', '0001_initial')]
    # Django guards forward execution; explicitly guard reversals on SQLite as well.
    operations = [VendorSafeUnaccentExtension(), VendorSafeTrigramExtension()]
