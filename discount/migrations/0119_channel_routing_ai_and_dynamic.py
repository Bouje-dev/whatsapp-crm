# Weighted Chat Routing: AI percentage + dynamic offline redistribution

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('discount', '0118_channelagentrouting'),
    ]

    operations = [
        migrations.AddField(
            model_name='whatsappchannel',
            name='ai_routing_percentage',
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text='AI share of new leads when Full Autopilot is ON (0-100). Human percentages + this must equal 100.',
            ),
        ),
        migrations.AddField(
            model_name='whatsappchannel',
            name='dynamic_offline_redistribution',
            field=models.BooleanField(
                default=False,
                help_text='When ON, exclude offline agents and redistribute their percentages among online agents only.',
            ),
        ),
    ]
