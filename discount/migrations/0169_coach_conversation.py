# Generated for per-conversation coach chat storage

import uuid
from collections import defaultdict

from django.db import migrations, models
import django.db.models.deletion


def migrate_legacy_coach_messages(apps, schema_editor):
    CoachConversation = apps.get_model("discount", "CoachConversation")
    CoachConversationMessage = apps.get_model("discount", "CoachConversationMessage")
    groups = defaultdict(list)
    for msg in CoachConversationMessage.objects.filter(conversation__isnull=True).order_by("created_at"):
        groups[(msg.channel_id, msg.user_id)].append(msg)
    for (channel_id, user_id), msgs in groups.items():
        if not msgs:
            continue
        first_user = next((m for m in msgs if m.role == "user" and (m.content or "").strip()), None)
        title = "New chat"
        if first_user:
            title = (first_user.content or "").strip()[:200] or title
        conv = CoachConversation.objects.create(
            id=uuid.uuid4(),
            channel_id=channel_id,
            user_id=user_id,
            title=title,
        )
        last_created = msgs[-1].created_at
        CoachConversation.objects.filter(pk=conv.pk).update(updated_at=last_created)
        for m in msgs:
            m.conversation_id = conv.id
            m.save(update_fields=["conversation_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0168_blockedcustomer"),
    ]

    operations = [
        migrations.CreateModel(
            name="CoachConversation",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("title", models.CharField(blank=True, default="", max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "channel",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="coach_conversations",
                        to="discount.whatsappchannel",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="coach_conversations",
                        to="discount.customuser",
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.AddIndex(
            model_name="coachconversation",
            index=models.Index(
                fields=["channel", "user", "-updated_at"],
                name="discount_co_channel_7f3a2b_idx",
            ),
        ),
        migrations.AddField(
            model_name="coachconversationmessage",
            name="conversation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="messages",
                to="discount.coachconversation",
            ),
        ),
        migrations.RunPython(migrate_legacy_coach_messages, migrations.RunPython.noop),
    ]
