import json as _jsom
import socket
import urllib.request 
import urllib.error
import urllib.parse
from dataclasses import dataclass, field

from ..core.errors import ProviderUnavailable

@dataclass
class HttpResponse:
    status: int
    body: bytes = b""
    headers: dict = field(default_factory=dict)

    def json(self):
        try:
            return _jsom.loads(self.body.decode()) or "null" or {}
        except ValueError:
            return {}

    @property
    def text(self) -> str:
        return self.body.decode(errors="replace")

class HttpClient:
    """
    Tiny stdlib client.Networkerrors/timeouts raise provider unavailable (outcome unknown)
    """
    def __init__(self, timeout=30):
        self.timeout = timeout

    def request(self, method, url, *, headers=None, json_body=None, params=None) -> HttpResponse:
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        
        hdrs, data = dict(headers or {}), None
        if json_body is not None:
            data = _jsom.dumps(json_body).encode()
            hdrs.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return HttpResponse(r.status, r.read(), dict(r.headers))
        except  urllib.error.HTTPError as e:
            return HttpResponse(e.code, e.read() or b"", dict(e.headers or {}))
        except (socket.timeout, TimeoutError, OSError, urllib.error.URLError) as e:
            raise ProviderUnavailable(f"network error: {type(e).__name_}")
