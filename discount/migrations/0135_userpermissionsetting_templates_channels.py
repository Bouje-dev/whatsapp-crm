from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('discount', '0134_voice_dialect_coupling'),
    ]

    operations = [
        migrations.AddField(
            model_name='userpermissionsetting',
            name='can_create_channels',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='userpermissionsetting',
            name='can_create_templates',
            field=models.BooleanField(default=False),
        ),
    ]
