# Human-in-the-Loop (HITL): ChatSession ai_enabled, handover_reason, last_manual_message_at; HandoverLog

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('discount', '0104_follow_up_node_and_task'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatsession',
            name='ai_enabled',
            field=models.BooleanField(default=True, help_text='If False, AI does not process messages; merchant handles the chat.'),
        ),
        migrations.AddField(
            model_name='chatsession',
            name='handover_reason',
            field=models.CharField(blank=True, help_text='e.g. Customer asked for human, Sentiment detected', max_length=120),
        ),
        migrations.AddField(
            model_name='chatsession',
            name='last_manual_message_at',
            field=models.DateTimeField(blank=True, null=True, help_text='When the merchant last sent a manual message.'),
        ),
        migrations.CreateModel(
            name='HandoverLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('customer_phone', models.CharField(db_index=True, max_length=32)),
                ('reason', models.CharField(blank=True, max_length=120)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('channel', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='handover_logs', to='discount.whatsappchannel')),
            ],
            options={
                'ordering': ['-created_at'],
                'verbose_name': 'Handover log',
                'verbose_name_plural': 'Handover logs',
            },
        ),
        migrations.AddIndex(
            model_name='handoverlog',
            index=models.Index(fields=['channel', 'created_at'], name='discount_han_channel_9a1b2c_idx'),
        ),
    ]
