"""
Encrypted-asset spoiler support on Message.

Adds two fields used to deliver a digital product securely from the dashboard:
  - `is_digital_delivery`: flags an outgoing fulfillment message that contains
    a sensitive asset (download URL, license key, credentials). The dashboard
    chat-bubble renderer uses this flag to draw the blurred spoiler UI.
  - `encrypted_asset`: Fernet-encrypted ciphertext of the sensitive asset.
    Plaintext is *never* emitted at list-time; it is only decrypted server-side
    by a strict owner-only POST endpoint.

The field is `TextField` (not `CharField(500)`) on purpose: Fernet ciphertext
plus base64 overhead routinely exceeds 500 chars for the very payloads this
feature exists to protect (signed S3 URLs, multi-line license blocks).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('discount', '0154_simpleorder_digital_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='is_digital_delivery',
            field=models.BooleanField(
                default=False,
                db_index=True,
                help_text=(
                    'True when this outgoing message carries a sensitive '
                    'digital asset (download URL/key) that must be revealed '
                    'only to the store owner via the secure reveal endpoint.'
                ),
            ),
        ),
        migrations.AddField(
            model_name='message',
            name='encrypted_asset',
            field=models.TextField(
                blank=True,
                null=True,
                help_text=(
                    'Fernet-encrypted sensitive payload (download URL, '
                    'license key, credentials). Never expose at rest or in '
                    'chat JSON; decrypt only inside the owner-gated reveal '
                    'endpoint.'
                ),
            ),
        ),
    ]
