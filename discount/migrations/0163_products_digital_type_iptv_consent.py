# IPTV legal shield — digital sub-type + seller consent

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0162_merchant_risk_audit"),
    ]

    operations = [
        migrations.AddField(
            model_name="products",
            name="digital_product_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("account", "Account / credentials"),
                    ("key", "Activation key / licence"),
                    ("iptv", "IPTV subscription"),
                ],
                help_text="Sub-category for digital goods (account, key, or IPTV). Physical products leave this empty.",
                max_length=20,
                null=True,
                verbose_name="Digital product type",
            ),
        ),
        migrations.AddField(
            model_name="products",
            name="legal_consent_iptv",
            field=models.BooleanField(
                default=False,
                help_text="Mandatory for IPTV products: seller accepts full legal liability and DMCA enforcement policy.",
                verbose_name="IPTV legal consent",
            ),
        ),
    ]
