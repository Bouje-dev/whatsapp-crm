from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0124_chatsession_sentinel_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="plan",
            name="max_channels",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                help_text="Max WhatsApp channels the owner can create; null = unlimited",
            ),
        ),
        migrations.AddField(
            model_name="plan",
            name="max_team_members",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                help_text="Max team members (excl. owner/bots); null = unlimited",
            ),
        ),
    ]
