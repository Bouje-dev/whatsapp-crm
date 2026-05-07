# ChatSession: short-term memory for AI Agent (channel + customer_phone, active_node, 24h window)

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0098_plan_multi_modal"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChatSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("customer_phone", models.CharField(db_index=True, max_length=32)),
                ("is_expired", models.BooleanField(default=False)),
                ("context_data", models.JSONField(blank=True, default=dict)),
                ("last_interaction", models.DateTimeField(auto_now=True)),
                (
                    "active_node",
                    models.ForeignKey(
                        blank=True,
                        help_text="Current product/AI node context",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="active_sessions",
                        to="discount.node",
                    ),
                ),
                (
                    "channel",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chat_sessions",
                        to="discount.whatsappchannel",
                    ),
                ),
            ],
            options={
                "verbose_name": "Chat session",
                "verbose_name_plural": "Chat sessions",
            },
        ),
        migrations.AddConstraint(
            model_name="chatsession",
            constraint=models.UniqueConstraint(
                fields=("channel", "customer_phone"),
                name="unique_channel_customer_session",
            ),
        ),
        migrations.AddIndex(
            model_name="chatsession",
            index=models.Index(fields=["channel", "customer_phone"], name="discount_ch_channel_7a8b0d_idx"),
        ),
    ]
