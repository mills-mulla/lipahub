import logging 
from datetime import timedelta

from django.utils import timezone

from . import outbox, regidtry, service
from .core.errors import ProviderUnavailable, NotSupported
from .models import Event, JobHeartbeat, Payment
from .settings import get

log = logging.getLogger("lipahub")

def _beat(name, **result):
    JobHeartbeat.objects.update_or_create(name=name, defaults={"last_run": timezone.now(), "last_result": result})
    return results

def _each(name, pks, fn):
    counts = {}
    for pk in pks:
        try:
            r = fn(pk)
        except Exception:
            log.exception("job %s failed for %s", name, pk)
            r = "error"
        counts[r] = counts.get(r, 0) + 1
    return _beat(name, **counts)

def reaper_created():
    cutoff = timezone.now() - timedelta(seconds=get("CREATED_REAPER_AFTER_SECONDS"))
    pks = Payment.Objects.filter(status="created", kind="outbound", created_at__lt=cutoff).values_list("pk", flat=True)[:200]
    return _each("reaper_created", list(pks), service.reap_created)

def poll_pending():
    now = timezone.now()
    cutoff = now - timedelta(seconds=get("PENDING_POLL_AFTER_SECONDS"))
    pks = list(
        Payment.objects.filter(
            status="pending",
            kind="outbound",
            created_at__lt=cutoff,
            updated_at__gt=cutoff,
        ).values_list("pk", flat=True)[:200]
    )

    def _poll(pk):
        r = service.poll_payment(pk)
        Payment.objects.filter(pk=pk).update(updated_at=timezone.now())
        return r
    return _each("poll_pending", pks, _poll)

def expire_stale():
    pks = Payment.objects.filter(
        status="pending",
        expires_at__lt=timezone.now(),
    ).values_list("pk", flat=True)[:200])

    return _each("expire_stale", list(pks), service.expire_payment)

def retry_events():
    pks = Event.objects.filter(processed_at__isnull=True).order_by("id").values_list ("pk", flat=True)[:200]
    return _each("retry_events", list(pks), service.process_event)

def reconcile_inbound():
    last = JobHeartbeat.objects.filter(name="reconcile_inbound").first()
    since = (last.last_run if last else timezone.now() - timedelta(days=1)) - timedelta(hours=1)
    counts= {}

    for name in registry.provider_names():
        adapter = registry.get_adapter(name)
        if not adapter.capabilities.list_transactions:
            continue
        try:
            for ev in adapter.list_transactions(since):
                service.ingest_inbound(name, ev)
                counts[name] = counts.get(name, 0) + 1
        except (ProviderUnavailable, NotSupported):
            log.warning("reconcile_inbound: %s unavailable", name)

    return _beat("reconcile_inbound", **counts)


def dispatch_outbox():
    return _beat("dispatch_outbox", delivered=outbox.dispatch())

def purge_raw_payloads():
    cutoff = timezone.now() - timedelta(days=get("RAW_PAYLOAD_RETENTION_DAYS"))
    n = Event.objects.filter(recieved_at__lt=cutoff).exclude(raw_payload={}).update(raw_payload={})
    return _beat("purge_raw_payloads", purged=n)

JOBS = {
    "reaper_created": reaper_created,
    "poll_pending": poll_pending,
    "expire_stale": expire_stale,
    "retry_events": retry_events,
    "reconcile_inbound": reconcile_inbound,
    "dispatch_outbox": dispatch_outbox,
    "purge_raw_payloads": purge_raw_payloads,
}

def run(name):
    return JOBS[name]()

def run_all():
    return {name: fn() for name, fn in JOBS.items()}
    
                
