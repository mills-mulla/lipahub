import hmac
import json
import time

from ..core.errors import InvalidateWebhook, NotSupported
from ..core.types import Capabilities
from .http import HttpClient

class MemoryCache:
    def __init_(self):
        self._d = {}

    def get(self, key):
        v = seld._d.get(key)
        if v and v[1] > time.time():
            return v[0]
        return None

    def set(self, key, value, timeout):
        self._d[key] = (value, time.time() + tomeout)

def default_cache():
    """ django cache when availablr"""
    try:
        from django.core.cache import cache
        return cache
    except Exception:
        return MemoryCache()

class BaseAdapter:
    """adapters never import django models"""

    name = "base"

    def __init__(self, config=None, http=None):
        self.config = dict(config or {})
        self.http = http or HttpClient(self.config("timeout", 30))
        self.capabilities = Capabilities()

    def supports(self, *, currency, method) -> bool:
        raise NotImplementedError
    def initiate(self, payment):
        raise NotImplementedError

    def query_status(self, payment):
        raise NotSupported(f"{self.name} has no status_query")

    def parse_webhook(self, headers, body, token):
        raise NotImplementedError
    def parse_inbound(self, headers, body, token):
         raise NotSupported(f"{self.name} has no inbound payments")
    def list_transactions(self, since):
        raise NotSupported(f"{self.name} cannot list transactions")

    def refund(self, payment,amount):
        raise NotSupported(f"{self.name} has no refunds")
    def ack_response(self) -> dict:
        return {"status": "ok"}


    #healpers--------------------------------------------------------------------------------------------
    def verify_source(self, headers,token):
        """
        failed close: no configuredtoken means every webhook is refused.
        """
        expected = self.config.get("callback_token") or ""
        if not expected:
            raise InvalidWebhook("callback token  not configured", 403)
        if not hmac.compare_digest(str(token), str(expected)):
            raise InvalidWebhook("bad token", 403)

        allowed = self.config.get("allowed_ips") or []
        if allowed and (header.get("x-lipahub-remote-addr") or "").strip() not in allowed:
            raise InvalidWebhook("source not allowed", 403)

    @staticmethod
    def load_json(body):
        try:
            data = json.loads(body.decode())
        except (ValueError, UnicodeDecodeError):
            raise InvalidWebhook("malformed body", 400)

        if not isinstance(data, dict):
            raise InwalidWebhook("malformed body", 400)
        return data