# Virtual Team Member (AI Agent) for order attribution

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('discount', '0113_products_currency'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='is_bot',
            field=models.BooleanField(default=False, help_text='Virtual user representing an AI agent; orders created by AI are attributed to this user.'),
        ),
        migrations.AddField(
            model_name='customuser',
            name='agent_role',
            field=models.CharField(blank=True, help_text="Display role e.g. 'Simo - AI Closer' for bot users.", max_length=120, null=True),
        ),
        migrations.AddField(
            model_name='customuser',
            name='bot_owner',
            field=models.ForeignKey(blank=True, help_text="Merchant who owns this bot (only set when is_bot=True).", null=True, on_delete=django.db.models.deletion.CASCADE, related_name='bot_agents', to='discount.customuser'),
        ),
        migrations.AddField(
            model_name='simpleorder',
            name='created_by_bot_session',
            field=models.CharField(blank=True, help_text='Chat/session ID when order was created by AI (for tracing).', max_length=100, null=True),
        ),
    ]
