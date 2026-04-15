# Generated manually for Checkout Mode (AI data collection)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('discount', '0122_products_required_order_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='products',
            name='checkout_mode',
            field=models.CharField(
                blank=True,
                choices=[
                    ('quick_lead', 'Quick Lead (Name & Phone only)'),
                    ('standard_cod', 'Standard COD (Name, Phone, City)'),
                    ('strict_cod', 'Strict COD (Full Address)'),
                ],
                default='standard_cod',
                help_text='Controls what information the AI Sales Agent collects: quick_lead, standard_cod, or strict_cod.',
                max_length=20,
                verbose_name='Checkout mode (AI data collection)',
            ),
        ),
    ]
