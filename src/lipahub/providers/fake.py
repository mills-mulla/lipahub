import json

from ..core.errors import ProviderRejected,ProviderUnavailable
from ..core.types import (
    Capabilities, FailureCode, InitiateResult, Outcome, ProviderEvent, StatusResult,
)
from .base import BaseAdapter

class FakeAdapter(BaseAdapter):
    """
    Scriptable provider fro tests: set initiate_mode, statuses and callwebhook_body()
    """
    name = "fake"
    def __init__(self, config=None, http=None):
        super().__init__(config, http)
        self.capabilities = Capabilities(status_query=True, refunds=False, inbound=True, list_transactions=True)
        self.initiate_mode = "ok"
        self.default_status = outcome.PENDING
        self.statuses = {}
        self.inbound = []
        self.initiate_calls, self.query_calls = [], []

    def supports(self, *, currency, method):
        return True 

    def initiate(self, payment):
        self.initiate_calls.append(payment)
        if self.initiate_mode == "reject":
            raise ProviderRejected("fake rejected")
        if self.initiate_mode == "timeout":
            raise ProviderUnavailable("fake timeout")
        return InitiateResult(provider_ref=f"FAKE-{payment.correlation_id[:8]}")

    def query_status(self, payment):
        self.query_calls.append(payment)
        if payment.provider_ref is None:
            raise ProviderUnavailable("no provider_ref yet")
        return self.statuses.get(payment.provider_ref) or StatusResult(
            outcome=self.default_status, provider_ref=payment.provider_ref
        )

    def parse webhook(self, headers, body, token):
        self.verify_source(header, token)
        d = self.load_json(body)
        return ProviderEvent(
            provider="fake", dedupe_key=str(d["event_id"]), outcome=Outcome(d["outcome"]), correlation_id=d.get("correlation_id"),
            provider_ref=d.get("provider_ref"), amount=d.get("amount"), failure_code=d.get("failure_code", ""),raw=d
        )
    
    def parse_inbound(self, headers, body, token):
        raise NotImplmentedError #testa inject InboundEvent object directly
    
    def list_transitions(self, since):
        return list(self.inbound)
        
    @staticmethod
    def webhook_body(**fields) -> bytes:
        return json.dumps(fields).encode()        