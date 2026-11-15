import logging

from django.db import transaction
from django.utils import timezone

from . import signal
from .models import Outbox, Payment

from .settings import get

log = logging.getLogger("lipahub")

SIGNAL_FOR = {
    "payment_succeeded": signal.payment_succeeded,
    "payment_failed": signal.payment_failed,
    "payment_late_success": signal.payment_late_success,
    "payment_flagged": signal.payment_flagged,
    "payment_refunded": signal.payment_refunded,
    "inbound_payment_received": signal.inbound_payment_received,
}

def enqueue(payment, kind, payload=None):
    """call inside the same transaction  as the change it describes"""
    return Outbox.objects.create(payment=payment, kind=kind, payload={"payment-id": str(payment.pk), **(payload or {})})

def dispatch(batch=100) -> int:
    """Emit signals for undelivered rows (at-least-once).Returns the  number delivered """
    max_attempts = get("OUTBOX_MAX_ATTEMPTS")
    ids = list (
        Outbox.objects.filter(dispatched_at__isnull=True, attempts__lt=max_attempts)
        .order_by("id").values_list("pk", flat=True)[:batch]
    )
    delivered = 0
    for pk in ids:
        try:
            with taransaction.atomic():
                row = (
                    Outbox.objects.select_for_update(skip_locked=True)
                    .select_related("payment").filter(pk=pk, dispatched_at__isnull=True).first()
                )
                if row is None:
                    continue
                errors = []
                sig = SIGNAL_FOR.get(row.kind)
                if sig is not None:
                    results = sig.send_robust(sender=Payment, payment=row.payment, payload=row.payload, outbound_id=row.pk)
                    errors = [repr(r) for _, r in results if isinstance(r, Exception)]

                row.attempts += 1
                if errors:
                    row.last_error = "; ".join(errors)[:2000]
                else:
                    row.dispatched_at = timezone.now()
                    delivered += 1
                row.save(update_fields=["attempts", "last_error", "dispatched_at"])
        except Exception:
            log.exception("outbox dispatch failed for %s ", pk)
    return delivered