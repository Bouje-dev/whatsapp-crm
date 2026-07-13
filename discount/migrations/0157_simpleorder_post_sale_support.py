"""Post-sale support fields on SimpleOrder for digital replacement workflow."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('discount', '0156_digital_asset_stock'),
    ]

    operations = [
        migrations.AddField(
            model_name='simpleorder',
            name='support_status',
            field=models.CharField(
                choices=[
                    ('none', 'None'),
                    ('awaiting_proof', 'Awaiting proof'),
                    ('under_review', 'Under review'),
                    ('resolved', 'Resolved'),
                    ('rejected', 'Rejected'),
                ],
                db_index=True,
                default='none',
                help_text=(
                    'Post-sale support state for completed digital orders. '
                    'Tracks complaint intake, proof collection, merchant review, and resolution.'
                ),
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='simpleorder',
            name='complaint_summary',
            field=models.TextField(
                blank=True,
                help_text="Brief AI-generated summary of the customer's support issue.",
                null=True,
            ),
        ),
    ]
