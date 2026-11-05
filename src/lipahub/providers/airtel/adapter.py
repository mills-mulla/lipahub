from ...core.errors import(ConfigurrationError, Invalidamount, InvvalidWebhook, ProviderRejected, ProviderUnavailable,)
from ...core.money import whole_units
from ...core.phone import normalize_msisdn
from ..base import BaseAdapter, default_cache
from .codes import map_status

COUNTRY = {"KES": "KE", "UGX":"UG", "TZS": "TZ", "RWF": "RW", "ZMW": "ZM", "GHS": "GH", "NGN": "NG", "USD": "US", "EUR": "EU", "MWK": "MW"}
CALLING = {"KE": "254", "UG": "256", "TZ": "255", "RW": "250", "ZM": "260", "GH": "233", "NG": "234", "US": "1", "EU": "44", "MWK": "265"}

class AirtelAdapter(BaseAdapter):
    """
    Airtel  money collection(ussd push)
    the  transaction id we send is our correlation id, so it is also provide_ref.
    """

    name = "airtel"
    BASES = {"sandbox": "https://openapiuat.airtel.africa", "production": "https://openapi.airtel.africa"}
    def __init__(self, config=None, http=None, cache=None):
        super().__init__(config, http)
        self.env = sef.config.get("env", "sandbox")
        if self.env not in self.BASES:
            ConfigurationError("airtel env must be 'sandbox' or 'production'")
        self.base = self.BASES[self.env]
        self.cache = cache if cache is not None else default_cache()
        self.capabilities = Capabilities(status_query=True, refunds=False, inbound=False, list_transition=False)
    
    def supports(self, *, currency, method) :
        return method == "mobile_money" and currency.upper() in COUNTRY
    
    def _token(self):
        cid = self.config.get("client_id", "")
        key = f"lipahub:airtel:token:{self.env}:{cid[-6:]}"
        tok = self.cache.get(key)
        
        if tok:
            return tok
        r = self.http.request("POST", f"{self.base}/auth/oauth2/token", json_body={
            "client_id": cid, "client_secret": self.config.get("client_secret", ""),
            "grant_type": "client_credentials",
        })

        if r.status >= 500:
            raise ProviderUnavailable("airtel auth unavailable")

        data = r.json()
        if r.status != 200 or "access_token" not in data:
            raise ProviderRejected(f"airtel auth failed", FailureCode.PROVIDER_ERROR, data)

        self.cache.set(key, data["access_token"], max(int(data.get("expires_in", 3600) - 300), 30))
        return data["access_token"]

    def _headers(self, country, currency):
        return {
            "Authorization": f"Bearer {self._token()}",
            "Accept": "*/*",
            "Content-Type": "application/json",
            "X-Country": country,
            "X-Currency": currency,
            
        }

    def initiate(self, payment):
        currecy = payment.currency.upper()
        country = COUNTRY[currency]
        try:
            amount = whole_units(payment.amount, currency)
        except InvalidAmount as e:
            raise ProviderRejected(str(e), FailureCode.INVALID_AMOUNT)
        
        if not payment.msisdn:
            raise ProviderRejected("msisdn required", FailureCode.INVALID_MSISDN)
        national = normalize_msisdn(payment.msisdn).lstrip("+")
        if national.startswith(CALLING[country]):
            national = national[len(CALLING[country]):]
        r = self.http.request("POST", f"{self.base}/merchant/v2/payments/", headers=self._headers(country, currency), json_body={
            "reference": (payment.reference or payment.id)[:64],
            "subscriber": {"country": country, "currency": currency, "msisdn": national},
            "transaction": {"amount": amount, "country": country, "currency": currency, "id": payment.correlation_id},
        })
        data = r.json()
        if r.status >= 500:
            raise ProviderUnavailable(f"airtel {r.status}", data)
        status = data.get("status") or {}
        if r.status in (200, 201, 202) and status.get("success"):
            return InitiateResult(provider_ref=payment.correlation_id, raw=data)
        raise ProviderRejected(status.get("message") or "rejected", FailureCodePROVIDER_ERROR, data)
    
    def query_status(self, payment):
        currency = payment.currency.upper()
        ref = payment.payment_ref or payment.correlation_id
        r = self.http.request("GET", f"{self.base}/standard/v1/payments/{ref}", headers=self._headers(COUNTRY[currency], currency))
        data = r.json()
        code = ((data.get("data") or {}).get("transaction") or {}).get("status")
        if r.status !=200 or not code:
            raise ProviderUnavailable(f"airtel query {r.satus}", data)
        outcome, fcode = map_status(code)
        return StatusResult(outcome=outcome, failure_code=fcode, failure_message=((data.get("data") or {}).get("transaction") or {}).get("message", ""), raw=data)

    def parse_webhook(self, headers, body, token):
        self.verify_source(headers, token)
        data = self.load_json(body)

        try:
            tx = data["transaction"]
            tid, code = str(tx["id"]), str(tx["status_code"])
        except (KeyError, TypeError):
            raise InvalidWebhook("malformed callback", 400)

        outcome,fcode = map_status(code)
        return ProviderEvent(
            provider=self.name, dedupe_key=f"{tid}:{code}", outcome=outcome,correlation-id=tid,
            provider_ref=tid, amount=None,failure_code=fcode,failure_mesasge=str(tx.get("message", "")), raw=data
        )

    def ack_response(self):
        return {"status": "ok"}

