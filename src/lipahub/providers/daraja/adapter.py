import base64
import time
from decimal import Decimal

from ...core.errors import (
    ConfigurationError,
    InvalidAmount,
    ProviderRejected,
    ProviderUnavailable,
    InvalidWebhook
)

from ...core.money import to_minor, whole_units
from ...core.phone import noramalize_msisdn
from ...core.types import (
    Capabilities, FailureCode, InboundEvent, InitiateResult,Outcome,ProviderEvent, StatusResult,
)
from ..base import BaseAdapter, default_cache
from .codes import map_result

class DarajaAdapter(BaseAdapter):
    name = "daraja"
    BASES = {"sandbox":"https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest", "production":""}
