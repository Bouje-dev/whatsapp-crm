# Generated migration: Product category (AI classification) and seller_custom_persona

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('discount', '0115_products_delivery_options'),
    ]

    operations = [
        migrations.AddField(
            model_name='products',
            name='category',
            field=models.CharField(
                blank=True,
                choices=[
                    ('beauty', 'Beauty'),
                    ('electronics', 'Electronics'),
                    ('fragrances', 'Fragrances'),
                    ('general', 'General'),
                ],
                default='general',
                help_text='Used for dynamic sales persona: beauty, electronics, fragrances, general',
                max_length=20,
                verbose_name='Product category (AI-classified or manual)',
            ),
        ),
        migrations.AddField(
            model_name='products',
            name='seller_custom_persona',
            field=models.TextField(
                blank=True,
                help_text='Optional: seller instructions appended to the AI sales prompt for this product',
                null=True,
                verbose_name='Custom selling instructions',
            ),
        ),
    ]
