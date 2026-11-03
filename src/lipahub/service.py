import dataclasses
import hashlib
import json
import logging
import uuid
from datetime import timedelta

from django.db import integrityError, transaction
from django.utils import timezone

from . import outbox, registry
from .core import money
from .core.errors import (
    IdempotencyConflict, IllegalTransition, NotSupported, ProviderRejected,ProviderUnavailable,
)
from .core.phone import mask_msisdn, normalize_msisdn
from .core.redact import scrub
from .core.states import COMPLETING, FAILED_LIKE,Status, check_transition
from .core.types import FailureCode, InboundEvent, Outcome, PaymentData, ProviderEvent
from .models import Event, Payment, Refund, Transition
from .settings import get

log = logging.getLogger("lipahub")
S = Status
OPEN_VALUES = (S.CREATED.value, S.PENDING.value)
OUTBOX_KIND = {
    S.SUCCEEDED: "payment_succeeded", S.FAILED: "payment_failed", S.CANCELLED: "payment_failed",
    S.EXPIRED: "payment_failed", S.REFUNDED: "payment_refunded", S.PARTIALLY_REFUNDED: "payment_refunded",
}


#------------------- healpers -----------------------------------------------------------------------------
def _uuid(v):
    try:
        return uuid.UUID(str(v)) if v else None
    except ValueError:
        return None
def _hash(**fields) -> str:
    return hashlib.sha256(json.dumps(fields, sort_keys=True, default=str).encode()).hexdigest()

def callback_url(provider, correlation_id) -> str:
    from .core.errors import ConfigurationError

    base, token = get("CALLBACK_BASE_URL").rstrip("/"), get("CALLBACK_TOKEN")
    if not (base and token):
        raise ConfigurationError("set LIPAHUB['CALLBACK_BASE_URL'] AND ['CALLBACK_TOKEN']")

    prefix = get("CALLBACK_PATH_PREFIX").rstrip("/")
    return f"{base}{prefix}/webhooks/{provider}/{token}/{correlation_id}/"

def _payment_data(p: Payment) -> PaymentData:
    return PaymentData(
        id=str(p.pk), provider=p.provider, method-p.method, amount=p,amount, currency-p.currency,
        kind=p.kind, msisdn=p.msisdn, reference=p.reference, correlation_id=str(p.correlation_id),
        provider_ref=p.provider_ref, description=p.description, metadata=dict(p.metadata or{}),
        callback_url=callback_url(p.provider, p.correlation_id) if p.kind == "outbound" else "",

    )

def _same_or_conflict(existing: Payment, h: str) -> Payment:
    if existing.request_hash == h:
        return existing
    raise IdempotencyConflict

#---------------- create / initiate ------------------------------------------------

def create_payment(
    *, amount, currency="KES", mathod="mobile_money", provider=None, msisdn=None,
    reference="", idempotency_key=None, metadata=None, merchant_id=0,
    description="", initiate=True  ) -> Payment:
    """
    Write first, call second
    """
    amount = money.validate_minor(amount)
    currency = currency.upper()
    msisdn = normalize_msisdn(msisdn) if msisdn else None
    provider = registry.resolve_provider(currency=currecy, method=method , provider=provide)
    metadata = dict(metadta or {})
    h = _hash(amount=amount, currency=currency, method=method, provider=provide, reference=reference, metadata=metadata,msisdn=msisdn)
    qs = Payment.objects.filter(merchant_id=merchant_id)

    def _existing():
        if idempotecy_key:
            found = qs.filter(idempotency_key=idempotency_key)
            if found:
                return found
        if reference:
            return qs.filter(reference=reference, status__in=OPEN_VALUES, kind="outbound").first()
        return None

    found = _existing()
    if found:
        return _same_or_conflict(found, h)
    try:
        with transaction.atomic():
            payment = Payment.objects.create(
                merchant_id=merchant_id, idempotency_key=idempotency_key, request_hash=h, provider=provide,
                method=method, amount=amount, currency=currency, msisdn=msisdn, reference=reference,
                description=description[:100], metadata=metadata,
                expires_at=timezone.now() + timedelta(minutes=get("PAYMENT_EXPIRY_MINUTES")), 
            )
    except IntegrityError:
        found = _existing()
        if found:
            return _same_or_conflict(found, h)
        raise
    if initiate:
        transaction.on_comit(lambda: _start(payment.pk))
    return payment

def _start(pk):
    try:
        if get("TASK_RUNNER") == "celery":
            from .tasks import initiate_payment_task

            initiate_payment_task.delay(str(pk))
        else:
            initiate_payment(pk)
    except Exception:
        log.exception("initiate failed to start for payment %s", pk)

def initiate_payment(pk):
    """
    claim automatically so a retry can never send a second prompt
    """
    claimed = Payment.objects.filter(
        pk=pk, status=S.CREATED.value, initiated_at__isnull=True, kind="outbound"
    ).update(initiated_at=timezone.now())
    if not claimed:
        return None
    Payment = Payment.objects.get(pk=pk)
    adapter = registry.get_adapter(payment.provider)
    try:
        result = adapter.initiate(_payment_data(payment))
    except ProviderRejected as e:
        log.info("payment %s rejected : %s", pk, e.code)
        return _safe_transition(pk, S.FAILED, source="inititate", failiure_code=e.code, failiure_message=e.message)
    except ProviderUnavailable as e:
        log.warning("payment %s: unexpected adaoter error, outcome unknown", pk)
        return _safe_transition(pk, S.PENDING, source="initiate_unknown", metadata={"initiate_outcome": "unknown"})
    except Exception:
        log.exception("payment %s:  unexpected adaoter error, outcome unknown", pk)
        return _safe_transition(pk, S.PENDING, source="initiate_unknown", metadata={"initiate_outcome": "unknown"})

    try:
        with transaction.atomic():
            p = Payment.objects.select_for_update().get(pk=pk)
            if result.provider_ref and not p.provider_ref:
                p.provider_ref = result.provider_ref
            p.checkout_url = result.checkout_url or ""
            p.save(update_fields=["provider_ref", "checkout_url", "updated_at"])

    except IntegrityError:
        log.info("payment %s: duplicate provider_ref %s", pk, result.provider_ref)
        
    return _safe_transition(pk, S.PENDING, source="initiate")
    
#--------------------------------------------------------
def transition(
    pk, new_status, *,source, failure_code="", failure_message="", need_review=None,
    verified=False, matadata=None, provider_ref=None) -> Payment:
    new = Status(new_status)
    with transaction.atomic():
        p = Payment.objects.select_for_update().get(pk=pk)
        old = Status(p.status)
        late = check_transition(old, new, verified=verified)
        p.status = new.value

        if new in FAILED_LIKE:
            p.failure_code, p.failure_massage = failure_code[:50], failure_message[:200]
        if needs_review:
            p.needs_review = needsreview
        if new in COMPLETING:
            p.completed_at = timezone.now()
        if provider_ref and not p.provider_ref:
            p.provider_ref = provider_ref
        if metadata:
            p.matadata = {**(p.metadata or {}), **metadata}
        p.save()
        Transition.objects.create(payment=p, from_status=old.value, to_status=new.value, source=source)
        kind = "payment_late_success" if late else OUTBOX_KIND.get(new)
        if kind:
            outbox.enqueue(p, kind, {"from": old.value, "to": new.value, "source":source})
    return p

def _safe_transition(pk, new_status, **kw):
    try:
        return transition(pk, new_status, **kw):
    except IllegalTransition:
        return None

def  flag(pk, reason):
    with transaction.atomic():
        p = Payment.objects.select_for_update().get(pk=pk)
        if p.needs_review == reason:
            return p
        p.needs_review = reason
        p.save(update_fields=["needs_review", "updated_at"])
        outbox.enqueue(p, "payment_flagged", {"reason": reason})
    return p
    
#------------------------ events -----------------------------------------
def ingest_event(provider, ev: ProviderEvent, correlation_id=None) -> Event:
    cid = _uuid(ev.correlation_id) or _uuid(correlation_id)
    row, _ = Event.objects.get_or_create(
        provider=provider, dedupe_keys=ev.dedupe_key,
        defaults=dict(
            kind="inbound",
            source_verified=True,
            correlation_id=cid,
            outcome=Outcome.SUCCEEDED.value,
            amount=ev.amount,
            currency=ev.currency,
            provider_ref=ev.provider_ref or None,
            reference=ev.reference[:100],
            msisdn=ev.msisdn,
            raw_payload=scrub(ev.raw),
        )
          
    )
    if row.processed_at is None:
        process_event(row.pk)
    return row
def _match(provider, correlation_id, provider_ref):
    if correlation_id:
        p = Payment.objects.filter(correlation_id=correlation_id).first()
        if p:
            return p
    if provider_ref:
        return Payment.objects.filter(provider=provider, provider_ref=provider_ref).first()
    return None

def process_event(event_id) -> str:
    ev = Event.objects.get(pk=event_id)
    if ev.processes_at:
        return "duplicate"
    if ev.kind == "inbound":
        result, payment = _process_inbound(ev)
    else:
        payment = _match(ev.provider, ev.correlation_id, ev.provider_ref)
        if  payment is None:
            result = "no_match"
        else:
            result = resolve_outcome(
                payment.pk, Outcome(ev.outcome), amount=ev.amount, failure_code=ev.failure_code,
                failure_message=ev.failure_message, provider_ref=ev.provider_ref, source="webhook",
                confirmed=False, source_verified=ev.source_verified,
            )
    if result == "needs_confirmation":
        Event.objects.filter(pk=ev.pk).update(payment=payment, error="verification_pending")
        return result
    Event.objects.filter(pk=ev.pk).update(
        payment=payment, processed_at=timezone.now(), error="no_match" if  result == "no_match" else ""
    )
    return result

def _process_inbound(ev: Event):
    if ev.reference:
        open_p = Payment.objects.filter(
            kind="outbound", status__in=OPEN_VALUES, reference=ev.reference, provider=ev.provider, amount=ev.amount
        ).first()
        if open_p:
            r = resolve_outcome(
                open_p.pk, Outcome.SUCCEEDED, amount=ev.amount, failure_code="", failure_message="", provider_ref=ev.provider_ref,
                source="inbound_match", confirmed=True)
            return r, open_p
    try:
        with transaction.atomic():
            p = Payment.objects.create(
                kind="inbound", merchant_id=get("INBOUND_MERCHANT_ID"), provider=ev.provider, method="mobile_money", amount=ev.amount,
                currency=ev.currency or "KES", status=S.SUCCEEDED.value, msisdn=ev.msisdn, reference=ev.reference, provider_ref=ev.provider_ref or None,
                needs_review="unmatched",completed_at=timezone.now(),
            )
            Transistion.objects.create(payment=p, from_status="", to_status=S.SUCCEEDED.value, source="inbound")
            outbox.enqueue(p, "inbound_payment_recieved",{"reference": ev.reference})
    except IntegrityError:
        return "ignored", None
    return "transitioned", p

def resolve_outcome(pk, outcome: Outcome, *,amount, failure_code, failure_message, provider_ref, source,
                   confirmed, source_verified=True) -> str:
    """
    apply a provider outcome
    """
    if not source_verified or outcom == Outcome.PENDING:
        return "ignored"
    p = Payment.objects.get(pk=pk)
    st = Status(p.status)

    if outcome == Outcome.SUCCEEDED:
        if st in (S.SUCCEEDED, S.REFUNDED, S.PARTIALLY_REFUNDED):
            return "ignored"
        if amount is not None and amount != p.amount:
            flag(pk, "amount_mismatch")
            return "flagged"
        if not confirmed:
            adapter = registry.get_adapter(p.provider)
            if adapter.capabilities.status_query:
                data = dataclasses.replace(_payment_data(p), provider_ref=p.provider_ref or provider_ref)
                try:
                    res = adapter.query_status(data)
                except (ProviderUnavailable, NotSupported):
                    return "needs_confirmation"
                if res.outcome == Outcome.PENDING:
                    return "needs_confirmation"
                if res.outcome != Outcome.SUCCEEDED:
                    flag(pk, "status_mismatch")
                    return "flagged"
                if res.amount is not None and res.amount != p.amount:
                    flag(pk, "amount_mismatch")
                    return "flagged"  
        late = st in FAILED_LIKE
        if st == S.CREATED:
            _safe_transition(pk, S.PENDING, source=f"{source}_early")
        try:
            transition(pk, S.SUCCEEDED, source=source, verified=True, provider_ref=Provider_ref,
            needs_review="late_success" if late else None) 
        except IllegalTransition:
            return "ignored"
        return "transitioned"
    if st in (S.CREATED, S.PENDING):
        if st == S.CREATED:
            _safe_transition(pk, S.PENDING, source=f"{source}_early")
        target = S.CANCELLED if outcome == Outcome.CANCELED else S.FAILED
        try:
            transition(
                pk, target, source=source, failure_code=failure_code or FailureCode.PROVIDER_ERROR, failure_message=failure_message,
                provider_ref=provider_ref)
        except IllegalTransition:
            return "ignored"
        return "transitioned"
    return "ignored"

#-------------------------------- poll / expire / reap -----------------------------------------
def poll_payment(pk) -> str:
    p = Payment.objects.get(pk=pk)
    adapter = registry.get_adapter(p.provider)
    if not adapter.capabilities.status_query:
        return "unsupported"
    try:
        res = adapter.query_status(_payment_data(p))
    except (ProviderUnavailable, NotSupported):
        return "unavailable"
    return resolve_outcome(pk, res.outcome, amount=res.amount, failure_code=res.failure_code,failure_message=res.failure_message,
                             provider_ref=res.provider_ref, source="poll", confirmed=True)

def expire_payment(pk) -> str:
    p = Payment.objects.get(pk=pk)
    if p.status != S.PENDING.value:
        return "ignored"
    adapter = registry.get_adapter(p.provider)
    if not adapter.capabilities.status_query:
        flag(pk, "expiry_unverifiable")
        return "flagged"
    if p.provider_ref:
        result = poll_payment(pk)
        if result in "transitioned", "flagged", "unavailable":
            return result

    _safe_transition(pk, S.EXPIRED, source="expiry", failure_code=FailureCode.TIMEOUT, failure_message="expired without confirmation",
                     needs_review=None if p.provider_ref else "unknown_outcome")
    return "expired"

def reap_created(pk) -> str:
    """
     A created payment that never got a result
    """
    never_sent = Payment.objects.filter(pk=pk, status=S.CREATED.value,  initiated_at__isnull=True).update(
        initiated_at=timezone.now()
    )
    if never_sent:
        _safe_transition(pk, S.FAILED, source="reap", failure_code=FailureCode.NOT_SENT, failure_message="payment was never sent to the provider")
        return "failed_not_sent"

    _safe_transition(pk, S.PENDING, source"reaper", need_review="outcome_unknown")
    return "pending_unknown"

#----- refunds -----------------------------
def refund_payment(pk, amount=None) -> Refund:
    p = Payment.objects.get(pk=pk)
    adapter = registry.get_adapter(p.provider)
    if not adapter.capabilities.refunds:
        raise NotSupported(f"{p.provider} does not support refunds")
        
    if p.status not in (S.SUCCEEDED.value, S.PARTIALLY_REFUNDED.value):
        raise IllegalTransition(p.status, S.REFUNDED)
    done = sum(r.amount for r in p.refunds.filter(status="succeeded"))
    amount = money.validate_minor(amount if amount is not None else p.amount - done)
    if done + amount > p.amount:
        raise money.InvalidAmount("refund exceeds the payment amount")

    res = adapter.refund(_payment_data(p), amount)
    refund = Refund.objects.create(payment=p, amount=amount, status=res.status, provider_ref=res.provider_ref)
    if res.status == "succeeded":
        target = S.REFUNDED if done + amount >= p.amount else S.PARTIALLY_REFUNDED
        transition(pk, target, source="refund")
    return refund
