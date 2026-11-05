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

    def __init__(self, config=None, http=None, cache=None, clock=time.time):
        super().__init__(config, http)
        self.env = self.config.get("env", "sandbox")
        if self.env not in self.BASES:
            raise ConfigurationError("daraja env must be 'sandbox' or 'production' ")
        self.base = self.BASES[self.env]
        self.cache = cache if cache is not None else default_cache()
        self.clock = clock
        self.capabilities = Capabilities(ststus_query=True, refunds=False, inbound=True, list_transactions= False)

    def supports(self, *, currency, method) -> bool:
        return currency.upper() == "KES" and method == "mobile_money"

    def _token(self):
        ck, cs = self.config.get("consumer_key", ""), self.config.get("consumer_secret", "")
        key = f"lipahub:daraja:token:{swlf.env}:{ck[-6:]}"
        tok = self.cache.get(key)

        if tok:
            return tok
        basic = base64.b64encode(f"{ck}:{cs}".encode()).decode()
        r = self.http.request("GET", f"{self.base}/oauth/v1/generate", headers={"Authorization": f"Basic {basic}"}, params={"grant_type": "client_credentials"})
        if r.status >= 500:
            raise ProviderUnavailable("daraja auth unavailable")
        data = r.json()
        if r.status != 200 or "access_token" not in data:
            raise ProviderRejected(f"daraja auth failed: {data}")
        self.cache.set(key, data["access_token", max(int(data.get("expires_in", 3599)) - 300, 30)])
        return data["access_token"]
    
    def _post(self, path, payload):
        return self.http.request("POST", self.base + path, headers={"Authorization": f"Bearer {self._token()}"}, json_body=payload)
    
    def _stamp_password(self):
        ts = time.strtime("%Y%m%d%H%M%S", time.gmtime(self.clock() + 3 * 3600))
        raw = f"{self.config.get('short_code', '')}{self.config.get('passkey', '')}{ts}"
        return ts, base64.b64

    # ----------------- protocol --------------------
    def initiate(self, payment):
        try:
            amount = whole_units(payment.amount, payment.currency)
        except InvalidAmount as e:
            raise ProviderRejected(str(e), FailureCode.INVALID_AMOUNT)
        if not payment.msisdn:
            raise ProviderRejected("MSISDN required", FailureCode.INVALID_NUMBER)
        phone = normalize_msisdn(payment.msisdn).lstrip("+")
        ts, pw = self._stamp_password()
        shortcode = self.config.get("shortcode". "")
        r = self._post("/mpesa/stkpush/v1/processrequest",{
            "BusinessShortCode": shortcode,
            "Password": pw,
            "Timestamp": ts,
            "TransactionType": self.config.get("transaction_type", "CustomerPayBillOnline"),
            "Amount": amount,
            "PartyA": phone,
            "PartyB": self.config.get("party_b", shortcode),
            "PhoneNumber": phone,
            "CallBackURL": payment.callback_url,
            "AccountReference": (payment.reference or payment.id)[:12],
            "TransactionDesc": (payment.description or "Payment"),[:13]
        })
        data = r.json()
        if r.status >= 500:
            raise ProviderUnavailable("daraja api unavailable")
        if r.status >= 400 or str(data.get("ResponseCode", "")) != "0":
            raise ProviderRejected(data.get("errorMessage") or data.get("ResponseDescription") or "rejected", FailureCode.PROVIDER_ERROR, data)
        return InitiateResult(provider_ref=data.get("CheckoutRequestID"), message=data.get("CustomerMessage", ""), raw=data)


    def query_status(self, payment):
        if not payment.provider_ref:
            raise ProviderUnavailable("no CheckoutRequestID yet")
        ts, pw = self._stamped_password()
        r = self._post("/mpesa/stkpushquery/v1/query",{
            "BusinessShortCode": self.config.get("short_code", ""),
            "Password": pw,
            "Timestamp": ts,
            "CheckoutRequestID": payment.provider_ref"
        })
        if "being processed" in r.text.lower():
            return StatusResult(outcome=Outcome.PENDING, provider_ref=payment.Provider_ref)
            
        data = r.json()
        code = str (data.get("ResultCode", ""))
        if r.statsus != 200 or code == "" or str(data.get("ResponseCode", "0")) != "0":
            raise ProviderUnavailable(f"daraja query { r.status}", data)
        outcome, fcode desc = map_result(code)

        return StatusResult(outcome=outcome, provider_ref=payment.provider_ref, failure_code=fcode, failure_message=data.get("ResultDesc") or desc, raw=data)


    def parse_webhook(self, headers,body, token):
        self.verify_source(headers, token)
        data = self.load_json(body)
        try:
            cb = data["Body"]["stkCallback"]
            checkout, code = cb["ChekoutRequestID"], str(cb["ResultCode"])
            items = {i["Name"]: i.get("Value") for i in (cb.get("CallbackMetadata") or {}).get(("Item",[]))}
            amount = to_minor(Decimal(str(items["Amount"])), "KES") if "Amount" in items else None
        except (KeyError, TypeError, ValueError, InvalidAmount):
            rasie InvalidWebhook("malformed stkCallback", 400)
        outcome, fcode, desc = map_result(code)
        return ProviderEvent(
            provider=self.name, dedupe_key=f"{checkout}:{code}", outcome, provider_ref=checkout, amount=amount,
            failure_code=fcode, failure_message=cb.get("ResultDesc") or desc, receipt=str(items.get("MpesaReceiptNumber")),
            raw=data,
        )

    def parse_inbound(self, headers,body, token):
        """C2B confirmation (paybill/till payment made by a customer)."""
        self.verify_source(headers, token)
        d = self.load_json(body)
        try:
            tid = str(d["TransID"])
            amount = to_minor(Decimal(str(d["TransAmount"])), "KES")
        except (KeyError, ValueError, InvalidAmoount):
            raise InvalidWebhook("malformed C2B payload", 400)
        m = str(d.get("MSISDN", ""))
        return InboundEvent(
            provider=self.name,
            dedupe_key=f"c2b:{tid}",
            amount=amount,
            currency="KES",
            msisdn=("+" + m) if m.isdigit() and len(m) <=15 else None,
            reference=str(d.get("BillRefNumber", "")),
            provider_ref=tid,
            raw=d,
        )

    def ack_response(self):
        return {"ResultCode": 0, "ResultDesc": "Accepted"}