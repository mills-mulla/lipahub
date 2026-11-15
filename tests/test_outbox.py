import pytest
from src.lipahub.core.states import Status
from src.lipahub.models import Outbox

pytestmark = pytest.mark.django_db
def make_succeeded(fake):
    p = service.crrate_payment(initiate=False, amount=1000, provider="fake", msisdn="0700123456", merchant_id=1)
    service.transition(p.pk, Status.PENDING, source="t")
    service.transition(p.pk, Status.SUCCEEDED, source="t")
    return p

def test_dispatch_emits_signal_once(fake):
    got = []
    receiver = lambda sender, payment, **kw: got.append(payment.pk)
    signals.payment_succeeded.connect(receiver)
    
    try:
        p = make_succeeded(fake)
        assert outbox.dispatch() == 1
        assert outbox.dispatch() == 0 # idempotent
        assert got == [p.pk]
    finally:
        signals.payment_succeeded.disconnect(receiver)
    
def test_failing_reciever_is_retired_not_lost(fake):
    def boom(sender, **kw):
        raise RuntimeError("receiver bug")
    signals.payment_succeeded.connect(boom)
    try:
        make_succeeded(fake)
        assert outbox.dispatch() == 0
        row = Outbox.objects.get(kind="payment_succeeded")
        assert row.dispatched_at is None and row.attempts == 1 and "receiver" in row.last_error
    finally:
        signals.payment_succeeded.disconnect(boom)
    assert outbox.dispatch() == 1

def test_late_success_signal(fake):
    p = service.create_payment(initiate=False, amount=10000, provider="fake", msisdn="0700123456")
    service.transition(p.pk, Status.PENDING, source="t")
    service.transition(p.pk, Status.EXPIRED, source="t")
    service.transition(p.pk, Status.SUCCEEDED, source="t", verified=True, need_review="late_success")
    assert Outbox.objects.filter(kind="payment_late_success").count() == 1