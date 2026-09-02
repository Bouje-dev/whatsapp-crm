from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0170_rename_discount_co_channel_7f3a2b_idx_discount_co_channel_ef6373_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="googlesheetsconfig",
            name="auto_sync_ai_orders",
            field=models.BooleanField(
                default=True,
                help_text="When enabled, orders created by the AI agent are exported to Google Sheets automatically.",
            ),
        ),
    ]
