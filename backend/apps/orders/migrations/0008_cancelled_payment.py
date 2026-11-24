from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0007_order_order_payment_paid_at_idx_and_more")]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="payment_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pendiente"),
                    ("awaiting_manual_payment", "Pendiente de pago manual"),
                    ("approved", "Aprobado"),
                    ("declined", "Rechazado"),
                    ("error", "Error"),
                    ("expired", "Vencido"),
                    ("voided", "Anulado"),
                    ("cancelled", "Anulado"),
                ],
                default="pending", max_length=25, verbose_name="Estado del pago",
            ),
        ),
    ]
