from django.db import migrations


def english_default(apps, schema_editor):
    Settings = apps.get_model("core", "SiteSettings")
    Settings.objects.all().update(manual_payment_instructions_en=(
        "SERTI will share Efecty or transfer details via WhatsApp. "
        "Order {number}, total {total}. Pay before {deadline}."
    ))


class Migration(migrations.Migration):
    dependencies = [("core", "0004_sitesettings_certificate_price_cents_and_more")]
    operations = [migrations.RunPython(english_default, migrations.RunPython.noop)]
