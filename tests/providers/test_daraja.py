import base64
import json
import pytest

from src.lipahub.core.errors import InvalidWebhook, ProviderRejected, ProviderUnavailable
from src.lipahub.core.types import Outcome, PaymentData
from src.lipahub.providers.base import MemoryCache
from src.lipahub.providers.daraja import DarajaAdapter
from tests.test_contract import TOKEN, AdapterContract 
from tests.providers.scripted_http import ScriptedHttp


CFG = {"callback_token": TOKEN, "consumer_key": "ckckckck", "consumer_secret": "cs", "shortcode": "174379", "passkey": "pk"}
TOKEN_OK = {"access_token": "AT", "expires_in": "3599"}
STK_OK = {"CheckoutRequestID": "ws_CO_1", "ResponseCode": "0", "CustomerMessage": "Success"}

def callback(code=0, desc="ok", amount=150, with_meta=True):
    cb = {"MerchantRequestID": "ml", "CheckoutRequestID": "ws_CO_1", "ResultCode": code, "ResultDesc": desc}

    if with_meta:
        cb["CallbackMetadata"] = {"Item":[
            {"Name": "Amount", "Value": amount},
            {"Name": "MpesaRecieptNumber", "Value": "TESTEST"},
            {"Name": "PhoneNumber", "Value": 254700123456},
        ]}
    return json.dumps({"Body": {"stkCallback": cb}}).encode()

class TestDaraja(AdapterContract):
    def make(self, http=None):
        return DarajaAdapter(dict(CFG), http, cache=MemoryCache())
    
    def payment(self, **kw):
        d = dict(id="pl", provider="daraja", method="mpbile_money", amount=15000,  currency="KES", msisdn="+254700123456", reference="ORD-1",
        correlation_id="cid",callback_url="https://x/cb/")
        d.update(kw)
        return PaymentData(**d)
    def good_webhook(self):
        return {}, callback()
    
    def accept_initiate_http(self,http):
        http.push(200, TOKEN_OK).push(200, STK_OK)

    #--------- behaviour specific to daraja -----------
    def test_stk_payload(self):
        http = ScriptedHttp().push(200, TOKEN_OK).push(200, STK_OK)
        r = self.make(http).initiate(self.payment())
        assert r.provider_ref == "ws_CO_1"
        sent = http.calls[1]["json"]
        assert sent["Amount"] == 150 and sent["PhoneNumber"] == "254700123456"
        assert sent["CallBackURL"] == "https://x/cb/" and len(sent["AccountReference"]) <= 12
        assert http.calls[1]["headers"]["Authorization"] == "Bearer AT"
        assert base64.b64decode(sent["Password"]).decode().startswith("174379pk")

    def test_token_is_cached(self):
        http = ScriptedHttp().push(200, TOKEN_OK).push(200, STK_OK).push(200, STK_OK)
        a = self.make(http)
        a.initiate(self.payment())
        a.initiate(self.payment())

        assert sum("oauth" in c["url"] for c in http.calls) == 1

    def test_fractional_shillings_rejected_before_any_call(self):
        http = ScriptedHttp()

        with pytest.raises(ProviderRejected) as e:
            self.make(http).initiate(self.payment(amount=15050))
        assert e.value.code == "invalid_amount" and http.calls == []
    
    def test_5xx_is_unknown_outcome(self):
        http = ScriptedHttp().push(200, TOKEN_OK).push(500, {"errorMessage": "boom"})
        with pytest.raises(ProviderUnavailable):
            self.make(http).initiate(self.payment())
    
    def test_4xx_or_bad_response_code_is_rejection(self):
        http = ScriptedHttp().push(200, TOKEN_OK).push(200, {"ResponseCode": "1", "ResponseDescription": "no"})
        with pytest.raises(ProviderRejected):
            self.make(http).initiate(self.payment())

    def test_callback_success(self):
        ev = self.make().parse_webhook({}, callback(), TOKEN)
        assert ev.outcome == Outcome.SUCCEEDED and ev.amount == 15000
        assert ev.provider_ref == "ws_CO_1" and ev.receipt == "TESTEST"

    @pytest.mark.parametrize("code,outcome,fcode",[
        (1032, Outcome.CANCELED, "canceled_by_user"), 
        (2001, Outcome.FAILED, "wrong_pin"),
        (1, Outcome.FAILED, "insufficient_funds"),
        (1037, Outcome.FAILED, "timeout"),
        (5555, Outcome.FAILED, "provider_error"),
    ])
    def test_callback_failures(self, code, outcome, fcode):
        ev = self.make().parse_webhook({},callback(code, with_meta=True), TOKEN)
        assert ev.outcome == outcome and ev.failure_code == fcode and ev.amount is None

    
    def test_callback_missing_fields(self):
        with pytest.raises(InvalidWebhook):
            self.make().parse_webhook({}, json.dumps({"Body": {}}).encode(), TOKEN)

    def test_ip_allowlist(self):
        a = DarajaAdapter({**CFG, "allowed_ips": ["196.201.214.200"]}, cache=MemoryCache())
        with pytest.raises(InvalidWebhook):
            a.parse_webhook({"x-lipahub-remote-addr": "1.2.3.4"}, callback(), TOKEN)
        assert a.parse_webhook({"x-lipahub-remote-addr": "196.201.214.200"}, callback(), TOKEN)

    def test_query_success_failure_and_processing(self):
        p = self.payment(provider_ref="ws_CO_1")
        http = ScriptedHttp().push(200, TOKEN_OK).push(200, {"ResponseCode": "0", "ResultCode": "0", "ResultDesc": "ok"})
        assert self.make(http).query_status(p).outcome == Outcome.SUCCEEDED
        http = ScriptedHttp().push(200, TOKEN_OK).push(200, {"ResponseCode": "0", "ResultCode": "1032", "ResultDesc": "canceled"})
        assert self.make(http).query_status(p).outcome == Outcome.CANCELED
        http = ScriptedHttp().push(200, TOKEN_OK).push(500, {"errorMessage": "the transaction is being processed"})
        assert self.make(http).query_status(p).outcome == Outcome.PENDING

    def test_query_without_checkout_id_is_unknown(self):
        with pytest.raises(ProviderUnavailable):
            self.make().query_status(self.payment())

    def test_inbound_c2b(self):
        body = json.dumps({"TransID": "TESTEST", "TransAmount": "100.00", "MSISDN": "254700123456", "BillRefNumber": "ORD-1"}).encode()
        ev = self.make().parse_inbound({}, body, TOKEN)
        assert ev.amount == 10000 and ev.reference == "ORD-1" and ev.dedupe_key == "c2b:TESTEST"

    def test_ack_shape(self):
        assert self.make().ack_response() == {"ResultCode": 0, "ResultDesc": "Accepted"}

    


    

