# Generated manually for Smart Follow-up Node

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('discount', '0103_voicepersona_provider'),
    ]

    operations = [
        migrations.CreateModel(
            name='FollowUpNode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('delay_hours', models.PositiveIntegerField(default=6, help_text='Hours to wait before sending follow-up')),
                ('response_type', models.CharField(
                    choices=[('TEXT', 'Text'), ('AUDIO', 'Audio'), ('IMAGE', 'Image'), ('VIDEO', 'Video')],
                    default='TEXT', max_length=10)),
                ('ai_personalized', models.BooleanField(default=False, help_text='If True, GPT generates the follow-up based on conversation history')),
                ('file_attachment', models.FileField(blank=True, help_text='Pre-defined media for AUDIO/IMAGE/VIDEO', max_length=500, null=True, upload_to='follow_up_media/%Y/%m/')),
                ('caption', models.TextField(blank=True, help_text='Default message text or caption for media')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('node', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='follow_up_config', to='discount.node')),
            ],
            options={
                'verbose_name': 'Follow-up node config',
                'verbose_name_plural': 'Follow-up node configs',
            },
        ),
        migrations.CreateModel(
            name='FollowUpTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('customer_phone', models.CharField(db_index=True, max_length=32)),
                ('scheduled_at', models.DateTimeField(db_index=True)),
                ('is_cancelled', models.BooleanField(default=False)),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('SENT', 'Sent'), ('CANCELLED', 'Cancelled')], db_index=True, default='PENDING', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('channel', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='follow_up_tasks', to='discount.whatsappchannel')),
                ('node', models.ForeignKey(help_text='The follow-up node that created this task', on_delete=django.db.models.deletion.CASCADE, related_name='follow_up_tasks', to='discount.node')),
            ],
            options={
                'ordering': ['scheduled_at'],
                'verbose_name': 'Follow-up task',
                'verbose_name_plural': 'Follow-up tasks',
            },
        ),
        migrations.CreateModel(
            name='FollowUpSentLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('customer_phone', models.CharField(max_length=32)),
                ('node_id', models.PositiveIntegerField(blank=True, help_text='Follow-up Node id', null=True)),
                ('response_type', models.CharField(blank=True, max_length=10)),
                ('sent_at', models.DateTimeField(auto_now_add=True)),
                ('channel', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='follow_up_sent_logs', to='discount.whatsappchannel')),
            ],
            options={
                'ordering': ['-sent_at'],
                'verbose_name': 'Follow-up sent log',
                'verbose_name_plural': 'Follow-up sent logs',
            },
        ),
        migrations.AddIndex(
            model_name='followuptask',
            index=models.Index(fields=['channel', 'customer_phone', 'status'], name='discount_fol_channel_7a8b0d_idx'),
        ),
        migrations.AddIndex(
            model_name='followuptask',
            index=models.Index(fields=['status', 'scheduled_at'], name='discount_fol_status_8c9e1f_idx'),
        ),
        migrations.AddIndex(
            model_name='followupsentlog',
            index=models.Index(fields=['channel', 'sent_at'], name='discount_fol_channel_2d3e4a_idx'),
        ),
    ]
