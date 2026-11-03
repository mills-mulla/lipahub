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