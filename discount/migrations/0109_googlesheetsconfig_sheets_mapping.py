# Generated migration: add sheets_mapping for drag-and-drop field mapping

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0108_simpleorder_sheets_export_error"),
    ]

    operations = [
        migrations.AddField(
            model_name="googlesheetsconfig",
            name="sheets_mapping",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='[{"field": "customer_name", "header": "Customer Name"}, ...]',
            ),
        ),
    ]
