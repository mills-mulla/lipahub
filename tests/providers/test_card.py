import hashlib
import hmac
import json

import pytest

from src.lipahub.core.errors import InvalidWebhook, ProviderRejected
from src.lipahub.core.types import Outcome, PaymentData
from src.lipahub.providers.card import PaystackAdapter
from tests.test_contract import TOKEN, AdapterContract
from tests.providers.scripted_http import ScriptedHttp

SECRET = "sk_test_x"
CFG = {"callback_token": TOKEN, "secret_key": SECRET, "return_url": "https://shop/return"}
CID = "222222222-11111-111111-1111111-22222222"

def signed(event="charge.success", amount=5000):
    body = json.dumps({"event": event, "data": {"id": 99, "reference": CID,"amount": amount, "status": "success" }}).encode()
    return {"x-paystack-signature": hmac.new(SECRET.encode(), body, hashlib.sha512).hexdigest()}, body

class TestCard(AdapterContract):
    def make(self, http=None):
        return PaystackAdapter(dict(CFG), http)
    
    def payment(self, **kw):
        d = dict(id="p1", provider="card", method="card", amount=5000, currency="KES", correlation_id=CID, metadata={"email":"a@b.co"})
        d.update(kw)
        return PaymentData(**d)
    
    def good_webhook(self):
        return signed()
    
    def accept_initiate_http(self, http):
        http.push(200, {"status": True, "data": {"authorization_url": "https://checkout/x", "reference": CID}})

    def test_initiate_returns_checkout_url_and_minor_amount(self):
        http = ScriptedHttp()
        self.accept_initiate_http(http)
        r = self.make(http).initiate(self.payment())
        assert r.checkout_url == "https://checkout/x" and  r.provider_ref == CID
        assert http.calls[0]["json"]["amount"] == 5000 and http.calls[0]["json"]["reference"] == CID

    def test_email_reqired(self):
        with pytest.raises(ProviderRejected):
            self.make().initiate(self.payment(metadata={}))
        

    def test_bad_signature(self):
        headers, body = signed()
        with pytest.raises(InvalidWebhook) as e:
            self.make().parse_webhook({"x-paystack-signature": "00"}, body, TOKEN)
        assert e.value.status == 403


    def test_success_event_and_ignored_event(self):
        h, b = signed()
        ev = self.make().parse_webhook(h,b, TOKEN)
        assert ev.outcome == Outcome.SUCCEEDED and  ev.amount == 5000 and ev.correlation_id == CID
        h, b =signed(event="transfer.success")
        assert self.make().parse_webhook(h, b, TOKEN).outcome == Outcome.PENDING


    def test_verify(self):
        http = ScriptedHttp().push(200, {"data": {"status": "success", "amount": 5000}})
        r = self.make(http).query_status(self.payment())
        assert r.outcome == Outcome.SUCCEEDED and  r.amount == 5000
        assert  self .make(ScriptedHttp().push(404, {})).query_status(self.payment()).outcome == Outcome.PENDING
    
