import json
from src.lipahub.core.types import Outcome,PaymentData
from src.lipahub.providers.fake import FakeAdapter
from tests.test_contract import TOKEN, AdapterContract


class TestFake(AdapterContract):
    def make(self, http=None):
        return FakeAdapter({"callback_token": TOKEN}, http)
    
    def payment(self, **kw):
        d = dict(id="pl", provider="fake", method="mobile_money", amount=10000, currency="KES",msisdn="+254700123456", correlation_id="clclclcl-0000-0000-0000000000")
        d.update(kw)
        return PaymentData(**d)

    def good_webhook(self):
        return {}, FakeAdapter.webhook_body(event_id="e1", outcome="succeeded", correlation_id="c1")
    
    def accept_initiate_http(self, http):
        pass
    
    def test_initiate_timeout_is_unknown_outcome(self):
        import pytest
        from src.lipahub.core.errors import ProviderUnavailable

        a = self.make()
        a.initiate_mode = "timeout"
        with pytest.raises(ProviderUnavailable):
            a.initiate(self.payment())

    def test_initiate_makes_one_attempt_only(self):
        a = self.make()
        a.initiate(self.payment())
        assert len(a.initiate_calls) == 1

    def test_query_needs_provider_ref(self):
        import pytest
        from src.lipahub.core.errors import ProviderUnavailable

        with pytest.raises(ProviderUnavailable):
            self.make().query_status(self.payment())
