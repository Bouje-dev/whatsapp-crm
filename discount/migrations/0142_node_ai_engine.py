from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0141_chatsession_active_product"),
    ]

    operations = [
        migrations.AddField(
            model_name="node",
            name="ai_engine",
            field=models.CharField(
                blank=True,
                choices=[("AUTO", "Auto"), ("GPT_4O", "GPT-4o"), ("CLAUDE_3_5", "Claude 3.5")],
                default="AUTO",
                help_text="AI engine selection for this node: Auto, GPT-4o, or Claude 3.5.",
                max_length=20,
            ),
        ),
    ]
