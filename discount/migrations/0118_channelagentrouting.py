# Weighted Chat Routing: per-channel per-agent routing_percentage and is_accepting_chats

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('discount', '0117_products_category_choices'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ChannelAgentRouting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('routing_percentage', models.PositiveSmallIntegerField(default=0, help_text='Weight for new lead distribution (0-100). Sum for channel must be 100.')),
                ('is_accepting_chats', models.BooleanField(default=True, help_text='If False, agent is excluded from new assignments; existing sticky assignments remain.')),
                ('agent', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='channel_routing_configs', to=settings.AUTH_USER_MODEL)),
                ('channel', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='agent_routing_configs', to='discount.whatsappchannel')),
            ],
            options={
                'db_table': 'discount_channelagentrouting',
                'verbose_name': 'Channel Agent Routing',
                'verbose_name_plural': 'Channel Agent Routings',
                'unique_together': {('channel', 'agent')},
            },
        ),
    ]
