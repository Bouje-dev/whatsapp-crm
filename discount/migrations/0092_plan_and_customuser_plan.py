# Subscription plans and API security

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('discount', '0091_ai_voice_sales_settings'),
    ]

    operations = [
        migrations.CreateModel(
            name='Plan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, unique=True)),
                ('can_use_ai_voice', models.BooleanField(default=False)),
                ('can_use_voice_cloning', models.BooleanField(default=False)),
                ('can_use_auto_reply', models.BooleanField(default=False)),
                ('price', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
            ],
        ),
        migrations.AddField(
            model_name='customuser',
            name='plan',
            field=models.ForeignKey(
                blank=True,
                help_text='Subscription plan for API and feature access.',
                null=True,
                on_delete=models.SET_NULL,
                related_name='users',
                to='discount.plan',
            ),
        ),
    ]
