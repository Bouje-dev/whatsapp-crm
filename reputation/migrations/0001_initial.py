# Generated manually for Global Reputation app

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="GlobalCustomerProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phone_number", models.CharField(db_index=True, max_length=32, unique=True)),
                ("fingerprint_hash", models.CharField(blank=True, max_length=64)),
                ("total_orders_count", models.PositiveIntegerField(default=0)),
                ("delivered_count", models.PositiveIntegerField(default=0)),
                ("returned_count", models.PositiveIntegerField(default=0)),
                ("canceled_count", models.PositiveIntegerField(default=0)),
                ("no_answer_count", models.PositiveIntegerField(default=0)),
                ("last_order_date", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-last_order_date", "-updated_at"],
                "verbose_name": "Global Customer Profile",
                "verbose_name_plural": "Global Customer Profiles",
            },
        ),
        migrations.AddIndex(
            model_name="globalcustomerprofile",
            index=models.Index(fields=["-last_order_date"], name="rep_glob_last_order_idx"),
        ),
    ]
