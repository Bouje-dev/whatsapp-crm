from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0142_node_ai_engine"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappchannel",
            name="ai_llm_engine",
            field=models.CharField(
                blank=True,
                choices=[
                    ("AUTO", "Auto (dialect-based routing)"),
                    ("GPT_4O", "GPT-4o (OpenAI)"),
                    ("CLAUDE_3_5", "Claude 3.5 Sonnet (Anthropic)"),
                ],
                default="AUTO",
                help_text="Default LLM for AI agent replies on this channel. Flow node AI Engine overrides when set to GPT or Claude.",
                max_length=20,
            ),
        ),
    ]
