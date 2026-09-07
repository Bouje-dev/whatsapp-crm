from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0177_product_knowledge_gap"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappcheckoutstate",
            name="is_waiting_for_answer",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text=(
                    "True after a knowledge-gap escalation while the customer is paused waiting. "
                    "If still True when the merchant answers, WhatsApp the reply immediately; "
                    "otherwise queue it for the next AI turn."
                ),
            ),
        ),
        migrations.AddField(
            model_name="whatsappcheckoutstate",
            name="pending_knowledge_question",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Customer question waiting to be woven into the next AI reply.",
            ),
        ),
        migrations.AddField(
            model_name="whatsappcheckoutstate",
            name="pending_knowledge_answer",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Merchant answer to integrate on the next AI turn (not sent immediately).",
            ),
        ),
        migrations.AddField(
            model_name="knowledgegapescalation",
            name="magic_token_nonce",
            field=models.CharField(
                blank=True,
                default="",
                help_text="One-time nonce bound to the magic-link token; cleared when resolved.",
                max_length=64,
            ),
        ),
    ]
