from enum import Enum

from .errors import IllegalTransition

class Status(str, Enum):
    CREATED = "created",
    PENDING = "pending",
    SUCCEEDED = "succeeded",
    FAILED = "failed",
    CANCELLED = "cancelled",
    EXPIRED = "expired",
    REFUNDED = "refunded",
    PARTIALLY_REFUNDED = "partially_refunded",

S = Status
TRANSITIONS = {
    S.CREATED: {S.PENDING, S.FAILED},
    S.PENDING: {S.SUCCEEDED, S.FAILED, S.CANCELLED, S.EXPIRED},
    S.SUCCEEDED: {S.REFUNDED, S.PARTIALLY_REFUNDED},
    S.FAILED: {S.SUCCEEDED},
    S.CANCELLED: {S.SUCCEEDED},
    S.EXPIRED: {S.SUCCEEDED},
    S.REFUNDED: set(),
}
LATE_SUCCESS_FROM = {S.FAILED, S.CANCELLED, S.EXPIRED}
FAILED_LIKE = {S.FAILED, S.CANCELLED, S.EXPIRED}
COMPLETING = {S.SUCCEEDED, S.FAILED, S.CANCELLED, S.EXPIRED}
OPEN = {S.CREATED, S.PENDING}

def is_open(status) -> bool:
    """Returns True if the status is open, meaning it can still be completed or failed"""
    return Status(status) in OPEN

def is_late_success(old, new) -> bool:
    return Status(old) in LATE_SUCCESS_FROM and Status(new) == S.SUCCEEDED

def can_transition(old, new) -> bool:
        return Status(new) in TRANSISTIONS[Status(old)]

def check_transition(old, new, *, verified=False) -> bool:
    """Raises IllegalTransition if the transition is not allowed.Return true when it is a late success"""
    old, new = Status(old), Status(new)
    if new not in TRANSITIONS[old]:
        raise IllegalTransition(old, new)
    late = is_late_success(old, new)
    if late and not verified:
        raise IllegalTransition(old, new, "late success requires verification")
    return late