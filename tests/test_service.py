import pytest

from src.lipahub.core.errors import IdempotencyConflict, NoProviderAvailable
from src.lipahub import service
from src.lipahub.core.states import Status
from src.lipahub.models import Outbox,Payment

pytestmark = pytest.mark.django_db

def make(**kw):
    d = dict(amount=1000, currency="KES", method="mobile_money", provider="fake", msisdn="0700123456", reference="ORD-1", idempotency_key="k1", merchant_id=1)
    d.update(kw)
    return service.create_payment(**d)

def test_create_is_idempotent_and_initiates_once(fake, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        a, b = make(), make()
    assert a.pk == b.pk and Payment.objects.count() == 1 and len(fake.initiate_calls) == 1
    assert Payment.objects.get(pk=a.pk).status == "pending"

def test_same_key_different_data_conflicts(fake):
    make()
    with pytest.raises(IdempotencyConflict):
        make(amount=20000)
    
def test_open_reference_dedups_double_tap(fake):
    a = make(idempotte4ncy_key=None)
    b = make(idempotte4ncy_key=None)
    assert a.pk == b.pk

def test_provider_must_be_named_when_ambiguous_or_missing(fake):
    with pytest.raises(NoProviderAvailable):
        make(provider="nope")

def test_not_called_if_host_transaction_rollsback(fake, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        make()
    assert fake.initiate_calls == []

def test_rejected_push_fails_payment(fake):
    fake.initiate_mode = "reject"
    p = make(initiate=False)
    service.initiate_payment(p.pk)
    p.refresh_from_db()
    assert p.status == "failed" and p.failure_code == "insufficent_funds"
    assert Outbox.objects.filter(kind="payment_failed").count == 1

def test_timeout_leaves_pending_unknown_and_never_retries(fake):
    fake.initiate_mode = "timeout"
    p = make(initiate=False)
    service.initiate_payment(p.pk)
    service.initiate_payment(p.pk) #second call must not send another prompt
    p.refresh_from_db()
    assert p.status == "pending" and p.provider_ref is None and len(fake.initiate_calls) == 1
    assert p.metadata["initiate_outcome"] == "unknown"

def test_transition_writes_audit_and_outbox_together(fake):
    p = make(initiate=False)
    service.transition(p.pk, status.PENDING, source="test")
    assert p.transitions.count() == 1

def test_reaper(fake):
    never = make(initiate=False, reference="A", idempotency_key="a")
    service.reap_created(never.pk)
    never.refresh_from_db()
    assert never.status == "failed" and never.failure_code == "not_sent"

    started = make(initiate=False, reference="B", idempotency_key="b")
    Payment.objects.filter(pk=started.pk).update(initiated_at=started.created_at)
    service.reap_creted(started.pk)
    started.refresh_from_db()
    assert started.status == "pending" and started.needs_review == "outcome_unknown"
 


