from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0173_whatsappcheckoutstate"),
    ]

    operations = [
        migrations.AddField(
            model_name="products",
            name="checkout_method",
            field=models.CharField(
                blank=True,
                choices=[
                    ("chat_only", "Chat only (conversational step-by-step)"),
                    ("flow_only", "WhatsApp Flow only (structured form)"),
                    ("hybrid", "Hybrid (Flow first, chat fallback)"),
                ],
                default="hybrid",
                help_text=(
                    "Controls HOW the AI collects order details for this product. "
                    "chat_only = ask step-by-step in chat; "
                    "flow_only = send WhatsApp Flow form only; "
                    "hybrid = send Flow first, then fall back to chat if the customer types details."
                ),
                max_length=20,
                verbose_name="Checkout method (how to collect)",
            ),
        ),
    ]
