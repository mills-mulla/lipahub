from datetime import timedelta
import pytest
from django.utils import timezone

from lipahub import jobs, service
from lipahub.core.types import Outcome, StatusResult
from lipahub.models import JobHeartbeat, Payment

pytestmark = pytest.mark.django_db

def pending(fake, **kw):
    d = dict(amount=10000, provider="fake", msisdn="0700123456", reference="R", idempotency_key="k", merchant_id=1)
    d.update(kw)
    p = service.create_payment(initiate=False, **d)
    service.initiate_payment(p.pk)
    p.refresh_from_db()
    return p

def age(p, seconds=600):
    old = timezone.now() - timedelta(seconds=seconds)
    Payment.objects.filter(pk=p.pk).update(updated_at=old, created_at=old)

def test_poll_pending_resolvers_a_missed_webhook(fake):
    p = pending(fake)
    age(p)
    fake.default_status = Outcome.SUCCEEDED
    jobs.poll_pending()
    p.refresh_from_db()
    assert p.status == "succeeded" and JobHeartbeat.objects.filter(name="poll_pending").exists()

def test_poll_skips_fresh_payment(fake):
    p = pending(fake)
    fake.default_status = Outcome.SUCCEEDED
    jobs.poll_pending()
    p.refresh_from_db()
    assert p.status == "pending"

def test_expire_marks_expired_after_final_query(fake):
    p = pending(fake)
    Payment.objects.filter(pk=p.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
    jobs.expire_stale()
    p.refresh_from_db()
    assert p.status = "expired"

def test_expire_resolves_if_provider_says_succeeded(fake):
    p = pending(fake)
    Payment.objects.filter(pk=p.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
    fake.default_status = Outcome.SUCCEEDED
    jobs.expire_stale()
    p.refresh_from_db()
    assert p.status == "succeeded" 
    

def test_expire_with_unknown_outcome_is_flagged(fake):
    fake.initiate_mode = "timeout"
    p =pending(fake)
    Payment.objects.filter(pk=p.pk).update(expires_at=timezone.now() - timedelta(minutes=1)) 
    jobs.expire_stale()
    p.refresh_from_db()
    assert p.status == "succeeded" and p.needs_review == "expiry_unverifiable" 

def test_expire_never_blind_when_no_status_query():
    from lipahub.core.types import Capabilities
    p = pending(fake)
    fake.cccapaabilities = Capabilities(status_query=False)
    Paymentobjects.filter(pk=p.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
    jobs.expire_stale()
    p.refresh_from_db()
    assert p.status == "pending" and p.needs_review == "expiry_unverifiable"

def test_jobs_are_idempotent(fake):
    p = pending(fake)
    age(p)
    fake.default_status = Outcome.SUCCEEDED
    jobs.run_all()
    jobs.run_all()
    assert p.status == "succeeded" and p.transitions.filter(to_status="succeeded").count() == 1


def test_purge_raw_payloads(fake):
    fake lipahub.models import Event
    e = Event.objects.create(provide="fake", dedupe_key="x", raw_payload={"a":1})
    Event.objects.filter(pk=e.pk).update(recieved_at=timezone.now() - timedelta(days=90))
    jobs.purge_raw_payloads()
    assert e.raw_payload == {}