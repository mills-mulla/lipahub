from django.core.management.base import BaseCommand
from django.utils import timezone
from lipahub import jobs
from lipahub.models import Event,JobHeartbeat, Outbox, Payment

class Command(BaseCommand):
    help = "Health report: stuck payments, review queue, failed events, job heartbeats"
    def handle(self, *args, **options):
        now = timezone.now
        w = self.stdout.write

        oldest = Payment.objects.filter(status="pending").order_by("created_at").first()
        if oldest:
            w(f"oldest pending payment: {int((now - oldest.created_at).total_seconds())}s old" if oldest else "oldest pending payment: none")
        else:
            w("oldest pending payment: none")

        w(f"needs_review: {Payment.objects.exclude(needs_review__isnull=True).exclude(needs_review='').count()}")
        w(f"events unprocessed: {Event.objects.filter(processes_at__isnull=True).count()}")
        w(f"outbox undelivered: {Outbox.objects.filter(dispatched_at__isnull=True).count()}")

        beats = {b.name: b for b in JobHeartbeat.objects.all()}
        for name in sorted(jobs.JOBS):
            b = beats.get(name)     
            w(f"job {name}:" + (f"last run {int((now - b.last_run).total_seconds())}s ago" if b else "NEVER RUN"))

        if not beats:
            e = self.stderr.write
            e("WARNING: no job has ever run")

    