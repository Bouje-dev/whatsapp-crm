"""
Dynamic Digital Stock — schema for FIFO-consumed digital credentials.

Adds:
  - `Products.stock_format`: tells the fulfillment pipeline how to parse
    each pre-loaded stock row ('single' or 'combo').
  - `DigitalAssetStock`: one row per ready-to-deliver credential. Each
    digital order approval locks ONE row with `select_for_update` inside
    `transaction.atomic`, marks it `is_sold=True`, and links it to the
    consuming `SimpleOrder`.

The compound index `(product, is_sold, id)` keeps the FIFO consume query
index-only even on large inventories.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('discount', '0155_message_digital_delivery_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='products',
            name='stock_format',
            field=models.CharField(
                choices=[
                    ('single', 'Single keys/codes (one per line)'),
                    ('combo',  'Email & Password (separated by ":")'),
                ],
                default='single',
                help_text=(
                    'Controls how each row of bulk-pasted digital stock is parsed '
                    'and delivered. "single" stores one opaque value per row; '
                    '"combo" expects "email:password" on every row.'
                ),
                max_length=16,
                verbose_name='Digital stock format',
            ),
        ),
        migrations.CreateModel(
            name='DigitalAssetStock',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('asset_content', models.TextField(
                    blank=True,
                    null=True,
                    help_text=(
                        'Fernet-encrypted credential payload (single key OR '
                        '"email:password" depending on product.stock_format).'
                    ),
                )),
                ('is_sold', models.BooleanField(
                    db_index=True,
                    default=False,
                    help_text='True once this row has been consumed and shipped to a customer.',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('sold_at', models.DateTimeField(
                    blank=True,
                    null=True,
                    help_text='Timestamp when this row was marked is_sold=True. '
                              'Useful for analytics and race-condition forensics.',
                )),
                ('product', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='digital_stock',
                    to='discount.products',
                    help_text='The digital product this asset will be delivered for.',
                )),
                ('order', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='digital_stock_rows',
                    to='discount.simpleorder',
                    help_text='The order that consumed this row (null while is_sold=False).',
                )),
            ],
            options={
                'ordering': ['id'],
                'indexes': [
                    models.Index(
                        fields=['product', 'is_sold', 'id'],
                        name='digstock_consume_idx',
                    ),
                ],
            },
        ),
    ]
