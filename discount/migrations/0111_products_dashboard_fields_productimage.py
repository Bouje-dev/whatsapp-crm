# Generated migration for Products dashboard fields and ProductImage

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('discount', '0110_simpleorder_expected_delivery_date_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='products',
            name='price',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='السعر'),
        ),
        migrations.AddField(
            model_name='products',
            name='description',
            field=models.TextField(blank=True, null=True, verbose_name='الوصف'),
        ),
        migrations.AddField(
            model_name='products',
            name='how_to_use',
            field=models.TextField(blank=True, null=True, verbose_name='طريقة الاستخدام'),
        ),
        migrations.AddField(
            model_name='products',
            name='offer',
            field=models.CharField(blank=True, max_length=500, null=True, verbose_name='العرض'),
        ),
        migrations.AddField(
            model_name='products',
            name='testimonial',
            field=models.FileField(blank=True, help_text='Optional: audio, video or image testimonial', null=True, upload_to='product_testimonials/%Y/%m/', verbose_name='شهادة صوت/فيديو/صورة'),
        ),
        migrations.AlterField(
            model_name='products',
            name='sku',
            field=models.CharField(blank=True, max_length=100, null=True, unique=True),
        ),
        migrations.CreateModel(
            name='ProductImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(upload_to='products/%Y/%m/')),
                ('order', models.PositiveIntegerField(default=0)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='images', to='discount.products')),
            ],
            options={
                'ordering': ['order', 'id'],
            },
        ),
    ]
