import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0176_whatsapp_ad_attribution"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductKnowledgeBase",
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
                (
                    "question",
                    models.TextField(
                        help_text="Customer question the AI could not answer from the description."
                    ),
                ),
                (
                    "answer",
                    models.TextField(
                        help_text="Merchant-provided answer; treated as product fact going forward."
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="knowledge_entries",
                        to="discount.products",
                    ),
                ),
            ],
            options={
                "verbose_name": "Product knowledge entry",
                "verbose_name_plural": "Product knowledge base",
                "ordering": ["-updated_at"],
            },
        ),
        migrations.AddIndex(
            model_name="productknowledgebase",
            index=models.Index(
                fields=["product", "updated_at"],
                name="discount_pkb_prod_upd_idx",
            ),
        ),
        migrations.CreateModel(
            name="KnowledgeGapEscalation",
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
                ("question", models.TextField()),
                ("answer", models.TextField(blank=True, default="")),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("resolved", "Resolved")],
                        db_index=True,
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "channel",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="knowledge_gap_escalations",
                        to="discount.whatsappchannel",
                    ),
                ),
                (
                    "knowledge_entry",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="escalations",
                        to="discount.productknowledgebase",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="knowledge_gap_escalations",
                        to="discount.products",
                    ),
                ),
            ],
            options={
                "verbose_name": "Knowledge gap escalation",
                "verbose_name_plural": "Knowledge gap escalations",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="knowledgegapescalation",
            index=models.Index(
                fields=["channel", "status", "created_at"],
                name="discount_kge_ch_st_dt_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="knowledgegapescalation",
            index=models.Index(
                fields=["channel", "customer_phone", "status"],
                name="discount_kge_ch_ph_st_idx",
            ),
        ),
    ]
