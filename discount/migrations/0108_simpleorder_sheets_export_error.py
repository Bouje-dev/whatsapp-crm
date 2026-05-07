# Manual migration: add sheets_export_error to SimpleOrder

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('discount', '0107_googlesheetsconfig_googlesheetsnode_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='simpleorder',
            name='sheets_export_error',
            field=models.TextField(
                blank=True,
                null=True,
                help_text='Last error message when Google Sheets sync failed (e.g. Permission Denied).',
            ),
        ),
    ]
