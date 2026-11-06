import pytest

from lipahub.core.errors import InvalidWebhook, ProviderUnavailable
from lipahub.core.types import Capabilities, Initiateresult, PaymentData

TOKEN = "tok"

class AdapterContract:
    