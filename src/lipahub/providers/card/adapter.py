import hashlib
import hmac

from ...core.errors import InvalidWebhook, ProviderRejected, ProviderUnavailable
from ...core.types import Capabilities, FailureCode, InitiateResult, Outcome, ProviderEvent, StatusResult
from ..base import BaseAdapter
from .codes import map_status

class PaystackAdapter(BaseAdapter):
    """
    hosted check out only
    """

    name = "card"
    BASE = "https://api.paystack.co"

    def  __init__(self, config=None, http=None):
        super().__init__(config, http)

        self.capabilities = Capabilities(status_query=True, refund=False, inbound=False, list_transitions=False)
    
    def support(self, *, currency,method):
        return method == "card" and currency.upper() in self.config.get("currencies", ["KES", "NGN", "GHS", "ZAR","UDD"]) 

    def auth(self):
        return {"Authorisation": f"Bearer {self.config.get('secret_key', '')}"}

    def initiate(self, payment):
        email = (payment.metadata or {}).get("email", "")
        if not email:
            raise ProviderRejected("metadata['email'] is required for card payments ", FailureCode.PROVIDER_ERROR)

        r = self.http.request("POST", F"{self.BASE}/transaction/initialize",
            headers=self.auth(),
            json={

                "amount": payment.amount,
                "email": email,
                "currency": payment.currency.upper(),
                "reference": payment.correlation_id,
                "callback_url": self.config.get("return_url", ""),
                "metadata": {
                    "payment_id": payment.id,
                }
            }
        ) 

        data = r.json()
        if r.status >= 500:
            raise ProviderUnavailable(f"paystacks {r.status}", data)
        d = data.get("data", {})
        if r.status == 200 and data.get("status") and d.get("authorization_url"):
            return InitiateResult(provider_ref=payment.correlation_id, checkout_url=d["authorization_url"], raw=data)
        raise ProviderRejected(data.get("message") or "rejected" , FailureCode.PROVIDER_ERROR, data)

    def query_status(self, payment):
        ref = payment.provider_ref or payment.correlation_id
        r = self.http.request("GET", f"{self.BASE}/transaction/verify/{ref}",
            headers=self.auth()
        )

        if r.status == 404:
            return StatusResult(outcome=Outcome.PENDING, provider_ref=ref)

        data = r.json()
        d = data.get("data", {})
        if r.status != 200 or nit d.get("status"):
            raise ProviderUnavailable(f"paystack verify {r.status}", data)
        outcome, fcode = map_status(d["status"])
        amount = d.get("amount") if outcome == Outcome.SUCCEEDED else None
        return StatusResult(
            outcome=outcome,
            amount=amount,
            provider_ref=ref,
            failure_code=fcode,
            failure_message=d.get("gateway_response",""), 
            raw=data
        )

    def parse_webhook(self, headers, body, token):
        self.verify_source(headers, token)
        expected = hmac.new(self.config.get("secret_key", "").encode(), body, hashlib.sha512).hexdigest()
        if not hmac.compare_digest(expected, headers.get("X-Paystack-Signature", "")):
            raise InvalidWebhook("bad signature", 403)

        data = self.load_json(body)
        event, d= data.get("event"), data.get("data") or {}
        if not d.get("reference"):
            raise InvalidWebhook("malformed event", 400)
        ok = event == "charge.success"
        return ProviderEvent(
            provider=self.name, dedupe_key=f"{event}:{d.get('id', d['reference'])}", outcome=Outcome.SUCCEEDED  if ok else Outcome.PENDING,
            correlation_id=d["reference"], provider_ref=d["reference"], amount=d.get("amount") if ok else None, raw=data
        )



