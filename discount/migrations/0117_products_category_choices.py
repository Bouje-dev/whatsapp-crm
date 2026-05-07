# Extend product category choices to match AI classifier (health_and_supplements, etc.)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('discount', '0116_products_category_seller_custom_persona'),
    ]

    operations = [
        migrations.AlterField(
            model_name='products',
            name='category',
            field=models.CharField(
                blank=True,
                choices=[
                    ('beauty_and_skincare', 'Beauty & Skincare'),
                    ('electronics_and_gadgets', 'Electronics & Gadgets'),
                    ('fragrances', 'Fragrances'),
                    ('fashion_and_apparel', 'Fashion & Apparel'),
                    ('health_and_supplements', 'Health & Supplements'),
                    ('home_and_kitchen', 'Home & Kitchen'),
                    ('general_retail', 'General'),
                    ('beauty', 'Beauty'),
                    ('electronics', 'Electronics'),
                    ('general', 'General'),
                ],
                default='general_retail',
                help_text='Used for dynamic sales persona: beauty, electronics, fragrances, general',
                max_length=32,
                verbose_name='Product category (AI-classified or manual)',
            ),
        ),
    ]
