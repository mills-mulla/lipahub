import json
import pytest

from src.lipahub.core.errors import ProviderRejected, ProviderUnavailable
from src.lipahub.core.types import Outcome, PaymentData
from src.lipahub.providers.base import MemoryCache
from src.lipahub.providers.airtel import AirtelAdapter
from tests.test_contract import TOKEN, AdapterContract 
from tests.providers.scripted_http import ScriptedHttp

CFG = {"callback_token": TOKEN, "client_id": "cidcid", "client_secret": "s"}
TOKEN_OK = {"access_token": "AT", "expires_in": 7200}
INIT_OK = {"status": {"success": True, "message": "ok"}, "data":{"transaction": {"id": "x", "status": "TIP"}}}
CID = "1111111-11111-111111-1111111-111111111111"

def cb(code="TS"):
    return json.dumps({"transaction": {"id": CID, "message": "m", "status_code": code, "airtel_money_id": "A1"}}).encode()

class TestAirtel(AdapterContract):
    def make(self, http=None):
        return AirtelAdapter(dict(CFG), http, cache=MemoryCache())

    def payment(self, **kw):
        d = dict(id="P1", provider="airtel", method="mobile_money", amount=20000, currency="KES", msisdn="+254733123456", reference="ORD-2", correlation_id=CID)
        d.update(kw)
        return PaymentData(**d)

    def good_webhook(self):
        return {}, cb()

    def accept_initiate_http(self, http):
        http.push(200, TOKEN_OK).push(200, INIT_OK)

    def test_payload_uses_national_number_and_country_headers(self):
        http = ScriptedHttp().push(200 , TOKEN_OK).push(200, INIT_OK)
        r = self.make(http).initiate(self.payment())
        assert r.provider_ref == CID
        call = http.calls[1]
        assert call["json"]["subscriber"]["msisdn"] == "733123456"
        assert call["json"]["transaction"] == {"amount": 20000, "country": "KE", "currency": "KES", "id": CID}
        assert call["headers"]["X-Country"] == "KE" and call["headers"]["X-currency"] == "KES"

    def test_rejection_and_5xx(self):
        http = ScriptedHttp().push(200, TOKEN_OK).push(200, {"status": {"success": False, "message": "no"}})
        with pytest.raises(ProviderRejected):
            self.make(http).initiate(self.payment())
        http = ScriptedHttp().push(200, TOKEN_OK).push(503, {})
        with pytest.raises(ProviderUnavailable):
            self.make(http).initiate(self.payment())

    @pytest.mark.parametrize("code, outcome", [("TS", Outcome.SUCCEEDED), ("TF", Outcome.FAILED), ("TE", Outcome.FAILED), ("TA", Outcome.PENDING), ("TIP", Outcome.PENDING)])

    def test_callback_mapping(self, code, outcome):
        ev = self.make().parse_webhook({}, cb(code), TOKEN)
        assert ev.outcome == outcome and ev.correlation_id == CID and ev.amount is None

    def test_query(self):
        http = ScriptedHttp().push(200, TOKEN_OK).push(200, {"data": {"transaction": {"status": "TS", "message":"ok"}}})
        assert self.make(http).query_status(self.payment()).outcome == Outcome.SUCCEEDED
        http = ScriptedHttp().push(200, TOKEN_OK).push(500, {})
        with pytest.raises(ProviderUnavailable):
            self.make(http).query_status(self.payment())
    
    def test_support(self):
        a = self.make()
        assert a.supports(currency="KES", method="mobile_money") and not a.supports(currency="EUR", method="mobile_money") 