import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0175_whatsappcheckoutstate_customer_notes"),
    ]

    operations = [
        migrations.AddField(
            model_name="simpleorder",
            name="ad_source_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Meta CTWA referral source_id (ad id) captured at chat start.",
                max_length=128,
            ),
        ),
        migrations.AddField(
            model_name="simpleorder",
            name="ad_source_url",
            field=models.URLField(
                blank=True,
                default="",
                help_text="Meta CTWA referral source_url for the originating ad.",
                max_length=500,
            ),
        ),
        migrations.AddField(
            model_name="simpleorder",
            name="ad_headline",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Meta CTWA ad headline from the referral object.",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="whatsappcheckoutstate",
            name="ad_source_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Meta CTWA referral source_id (ad id).",
                max_length=128,
            ),
        ),
        migrations.AddField(
            model_name="whatsappcheckoutstate",
            name="ad_source_url",
            field=models.URLField(
                blank=True,
                default="",
                help_text="Meta CTWA referral source_url.",
                max_length=500,
            ),
        ),
        migrations.AddField(
            model_name="whatsappcheckoutstate",
            name="ad_headline",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Meta CTWA ad headline from the referral object.",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="whatsappcheckoutstate",
            name="ad_attributed_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text="When the current CTWA referral was last saved onto this session.",
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name="whatsappcheckoutstate",
            index=models.Index(
                fields=["channel", "ad_source_id"],
                name="discount_wh_ch_adsrc_idx",
            ),
        ),
        migrations.CreateModel(
            name="WhatsAppAdClick",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("customer_phone", models.CharField(db_index=True, max_length=32)),
                ("ad_source_id", models.CharField(db_index=True, max_length=128)),
                (
                    "ad_source_url",
                    models.URLField(blank=True, default="", max_length=500),
                ),
                (
                    "ad_headline",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "channel",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ad_clicks",
                        to="discount.whatsappchannel",
                    ),
                ),
            ],
            options={
                "verbose_name": "WhatsApp ad click",
                "verbose_name_plural": "WhatsApp ad clicks",
            },
        ),
        migrations.AddIndex(
            model_name="whatsappadclick",
            index=models.Index(
                fields=["channel", "ad_source_id", "created_at"],
                name="discount_ad_ch_src_dt_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="whatsappadclick",
            index=models.Index(
                fields=["channel", "customer_phone", "created_at"],
                name="discount_ad_ch_ph_dt_idx",
            ),
        ),
    ]
