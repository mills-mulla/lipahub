import pytest
from src.lipahub import service
from src.lipahub.core.types import InboundEvent, Outcome, ProviderEvent
from src.lipahub.models import Event, Outbox, Payment


pytestmark = pytest.mark.django_db

def pending_payment(fake, **kw):
    d = dict(amount=10000, provider="fake", msisdn="0700123456", reference="ORD-1",  idempotency_key="k1", merchant_id=1)
    d.update(kw)
    p = service.create_payment (initiate=False, **d)
    service.initiate_payment(p.pk)
    p.refresh_from_db()
    return p

def event(p, outcome=Outcome.SUCCEEDED, key="e1", amount=None, **kw):
    return ProviderEvent(provider="fake", dedupe_key=key, outcome=outcome,correlation_id=str(p.correlation_id), provider_ref=p.provider_ref,
            amount=10000 if amount is None else amount, **kw)

def test_confirmed_success_transitions_once_and_replay_is_deduped(fake):
    p = pending_payment(fake)
    service.ingest_event("fake", event(p))
    service.ingest_event("fake", event(p))
    p.refresh_from_db()
    assert p.status == "succeeded" and Event.objects.count() == 1
    assert Outbox.objects.filter(kind="payment_succeded").count() == 1

def test_unconfirmed_success_waits_for_provider_staatus(fake):
    p = pending_payment(fake)
    service.ingest_event("fake", event(p))
    p.refresh_from_db()
    assert p.status == "pending" and Event.objects.get().error == "verification_pending"
    fake.default_status = Outcome.SUCCEEDED
    service.process_event(Event.objects.get().pk)
    p.refresh_from_db()
    assert p.status == "succeeded"

def test_forged_success_that_provider_denies_is_flagged(fake):
    p = pending_payment(fake)
    fake.default_status = Outcome.FAILED
    service.ingest_event("fake", event(p))
    p.refresh_from_db()
    assert p.status == "pending" and p.needs_review == "status_mismatch"

def test_amount_mismatch_never_transitions(fake):
    p = pending_payment(fake)
    fake.default_status =  Outcome.SUCCEEDED
    service.ingest_event("fake", event(p, amount=100))
    p.refresh_from_db()
    assert p.status == "pending" and p.needs_review == "amount_mismatch"

def test_early_callback_before_pending_is_handled(fake):
    p = service.create_payment(initiate=False, amount=10000, provider="fake", msisdn="0700123456", merchant_id=1)
    fake.default_status = Outcome.SUCCEEDED
    service.ingest_event("fake", ProviderEvent(provider="fake", dedupekey="e", outcome=Outcome.SUCCEEDED,
                        correlation_id=str(p.correlation_id), provider_ref="X", amount=10000))
    p.refresh_from_db()
    assert p.status == "succeeded"
    assert [t.to_status for t in p.transitions.order_by("id")] == ["pending", "succeeded"]

def test_failure_event_then_late_success_is_flagged(fake):
    p = pending_payment(fake)
    service.ingest_event("fake", event(p, Outcome.FAILED, key="f", failure_code="timeout"))
    p.refresh_from_db()
    assert p.status == "failed"
    fake.default_status = Outcome.SUCCEEDED
    service.ingest_event("fake", event(p, key="s"))
    p.refresh_from_db()
    assert p.status == "succeded" and p.needs_review == "late_success"
    assert Outbox.objects.filter(kind="payment_late_success").count() == 1


def test_success_event_for_unknown_payment_is_stored_not_dropped(fake):
    service.ingest_inbound("fake", InboundEvent(provider="fake", dedupekey="z", outcome=Outcome.SUCCEEDED,
                        correlation_id="1111111-11111-111111-1111111-111111111111", amount=1))
    assert Event.objects.get().error == "no_match"
   

def tes_inbound_unmatched_creates_flagged_payment(fake):
    service.ingest_inbound("fake", InboundEvent(provider="fake", dedupekey="c2b:1", amount=5000, reference="UNKNOWN",   provider_ref="rcpt1"))
    p.Payment.objects.get(kind="inbound")
    assert p.status == "succeeded" and p.needs_review == "unmatched"
    assert Outbox.objects.filter(kind="inbound_payment_recieved").count() == 1

def test_inbound_matching_open_payment_completes_it(fake):
    p = pending_payment(fake)
    service.ingest_inbound("fake", InboundEvent(provider="fake", dedupekey="c2b:2", amount=10000))
    p.refresh_from_db()
    assert p.status == "succeeded"


def test_phonenumbers_are_scrubbed_from_stored_payloads(fake):
    p = pending_payment(fake)
    service.ingest_event("fake", event(p, raw={"MSISDN": "254700123456"}))
    assert "700123" not in str(Event.objects.get().raw_payload)

def testwebhookview(fake, client):
    p = pending_payment(fake)
    fake.default_status = Outcome.SUCCEEDED
    body = faake.webhook_body(event_id="v1", outcome="succeeded", provider_ref=p.provider_ref, amount=10000)
    url = f"/lipahub/webhooks/fake/tok/{p.correlation_id}/"
    assert client.post("/lipahub/webhooks/fake/WRONG/", body, content_type="application/json").status_code == 403
    assert client.post(url, body, content_type="application/json").status_code == 200
    p.refresh_from_db()
    assert p.status == "succeeded"