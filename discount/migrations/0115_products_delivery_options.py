# Generated migration for Products.delivery_options

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('discount', '0114_virtual_team_member_bot_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='products',
            name='delivery_options',
            field=models.CharField(
                blank=True,
                help_text='e.g. "Free delivery", "30 MAD", "Free above 200 MAD" — shown to customer when they ask about delivery',
                max_length=500,
                null=True,
                verbose_name='خيارات التوصيل',
            ),
        ),
    ]
