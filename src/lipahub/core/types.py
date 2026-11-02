from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

class Outcome(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PENDING = "pending"
    CANCELED = "canceled"

class FailiureCode:
    CANCELLED_BY_USER = "cancelled_by_user"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    TIMEOUT = "timeout"
    WRONG_PIN = "wrong_pin"
    INVALID_AMMOUNT = "invalid_amount"
    INVALID_NUMBER = "invalid_number"   
    PROVIDER_ERROR = "provider_error"
    NOT_SENT = "not_sent"

@dataclass(frozen=True)
class Capabilities:
    status_query: bool = True
    refunds: bool = False
    inbound: bool = False
    list_transactions: bool = False

@dataclass(frozen=True)
class PaymentData:
    id: str
    provider: str
    method: str
    amount: int
    currency: str
    kind: str = "outbound"
    msisdn: Optional[str] = None
    reference: str = ""
    correlation_id: str = ""
    provider_ref: Optional[str] = None
    description: str = ""
    callback_url: str = ""
    metadata: dict = field(default_factory=dict)

@dataclass(frozen=True)
class InitiateResult:
    provider_ref: Optional[str] = None
    checkout_url: Optional[str] = None
    message: str = ""
    raw: dict = field(default_factory=dict)

@dataclass(frozen=True)
class ProviderEvent:
    provider: str
    dedupe_key:str
    outcome: Outcome
    correlation_id: Optional[str] = None
    provider_ref: Optional[str] = None
    amount: Optional[int] = None
    failure_code: str = ""
    failure_message: str = ""
    receipt: str = ""
    raw: dict = field(default_factory=dict)
    source_verified: bool = True

@dataclass(frozen=True)
class InboundEvent:
    provider: str
    dedupe_key: str
    amount: int
    currency: str = "KES"
    msisdn: Optional[str] = None
    reference: str = ""
    provider_ref: str = ""
    occured_at: Optional[datetime] = None
    raw: dict = field(default_factory=dict)
@dataclass(frozen=True)
class RefundResults:
    provider_ref: str = ""
    status: str = "succeeded"
    raw: dict = field(default_factory=dict)