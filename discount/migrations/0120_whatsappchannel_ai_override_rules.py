# AI Coaching: channel-level override rules from Admin

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('discount', '0119_channel_routing_ai_and_dynamic'),
    ]

    operations = [
        migrations.AddField(
            model_name='whatsappchannel',
            name='ai_override_rules',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Custom sales rules from Admin coaching; overrides default AI behavior for this channel.',
            ),
        ),
    ]
