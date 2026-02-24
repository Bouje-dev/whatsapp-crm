# SimpleOrder.created_by_ai; AIUsageLog for API usage tracking

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0099_chatsession"),
    ]

    operations = [
        migrations.AddField(
            model_name="simpleorder",
            name="created_by_ai",
            field=models.BooleanField(default=False, help_text="Order created via AI [ORDER_DATA] / save_order"),
        ),
        migrations.CreateModel(
            name="AIUsageLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(db_index=True)),
                ("provider", models.CharField(max_length=32)),
                ("characters_used", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "channel",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ai_usage_logs",
                        to="discount.whatsappchannel",
                    ),
                ),
            ],
            options={
                "ordering": ["-date", "-created_at"],
                "verbose_name": "AI usage log",
                "verbose_name_plural": "AI usage logs",
            },
        ),
        migrations.AddIndex(
            model_name="aiusagelog",
            index=models.Index(fields=["channel", "date"], name="discount_ai_channel_6b8c2a_idx"),
        ),
    ]
