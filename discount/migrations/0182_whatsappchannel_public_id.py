import secrets

from django.db import migrations, models

import discount.models


def fill_public_ids(apps, schema_editor):
    Channel = apps.get_model("discount", "WhatsAppChannel")
    used = set(
        Channel.objects.exclude(public_id__isnull=True)
        .exclude(public_id="")
        .values_list("public_id", flat=True)
    )
    missing = Channel.objects.filter(
        models.Q(public_id__isnull=True) | models.Q(public_id="")
    )
    for channel in missing.iterator():
        token = secrets.token_urlsafe(16)
        while token in used:
            token = secrets.token_urlsafe(16)
        used.add(token)
        Channel.objects.filter(pk=channel.pk).update(public_id=token)


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0181_rename_discount_kge_ch_st_dt_idx_discount_kn_channel_e84491_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappchannel",
            name="public_id",
            field=models.CharField(blank=True, editable=False, max_length=32, null=True, unique=True),
        ),
        migrations.RunPython(fill_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="whatsappchannel",
            name="public_id",
            field=models.CharField(
                default=discount.models.generate_channel_public_id,
                editable=False,
                help_text="Public unguessable id used in the messaging URL.",
                max_length=32,
                unique=True,
            ),
        ),
    ]
