"""
Run scheduled follow-up tasks (Smart Follow-up Node).
Call periodically via cron, e.g. every 5 minutes:
  * * * * * cd /path/to/project && python manage.py run_follow_up_tasks

Quiet hours (23:00–08:00): tasks are rescheduled to next 08:00, not sent.
"""
from django.utils import timezone
from django.core.management.base import BaseCommand

from discount.models import FollowUpTask
from discount.whatssapAPI.follow_up import run_follow_up_task


class Command(BaseCommand):
    help = "Process due follow-up tasks (send or reschedule if in quiet hours)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only list due tasks, do not send.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        qs = FollowUpTask.objects.filter(
            status=FollowUpTask.STATUS_PENDING,
            is_cancelled=False,
            scheduled_at__lte=now,
        ).select_related("channel", "node")
        count = qs.count()
        if count == 0:
            self.stdout.write("No due follow-up tasks.")
            return
        self.stdout.write(f"Processing {count} due follow-up task(s)...")
        dry_run = options.get("dry_run", False)
        sent = 0
        for task in qs:
            if dry_run:
                self.stdout.write(f"  Would process task {task.id} for {task.customer_phone} @ {task.scheduled_at}")
                continue
            if run_follow_up_task(task):
                sent += 1
        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f"Sent {sent} follow-up(s)."))
