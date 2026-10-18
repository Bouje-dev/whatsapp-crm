from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0182_whatsappchannel_public_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="failure_reason",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Why Meta rejected or failed this outbound message. Shown on the failed tick.",
            ),
        ),
    ]
