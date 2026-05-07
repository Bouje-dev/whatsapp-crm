# Generated manually for WhatsApp template document headers

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0136_extrachannelslotsubscription"),
    ]

    operations = [
        migrations.AddField(
            model_name="template",
            name="header_document",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="templates/headers/",
            ),
        ),
    ]
