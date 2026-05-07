# Generated manually for AI Sentinel checkpoint

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0123_add_product_checkout_mode"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatsession",
            name="consecutive_user_messages",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Increments per user message turn; checkpoint runs at threshold.",
            ),
        ),
        migrations.AddField(
            model_name="chatsession",
            name="requires_human",
            field=models.BooleanField(
                default=False,
                help_text="True when merchant should take over (e.g. sentinel flagged spam/time-wasting).",
            ),
        ),
        migrations.AddIndex(
            model_name="chatsession",
            index=models.Index(fields=["channel", "requires_human"], name="discount_ch_channel_4f8e2b_idx"),
        ),
    ]
