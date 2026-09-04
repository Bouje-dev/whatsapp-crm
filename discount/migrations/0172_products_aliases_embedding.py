from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0171_googlesheetsconfig_auto_sync_ai_orders"),
    ]

    operations = [
        migrations.AddField(
            model_name="products",
            name="aliases",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Alternative names, synonyms, or Darija variations used for exact product matching.",
                verbose_name="Aliases",
            ),
        ),
        migrations.AddField(
            model_name="products",
            name="embedding",
            field=models.JSONField(
                blank=True,
                help_text="OpenAI text-embedding-3-small vector (1536-d) of title + description.",
                null=True,
            ),
        ),
    ]
