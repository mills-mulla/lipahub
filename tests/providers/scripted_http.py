from lipahub.core.errors import ProviderUnavailable
from lipahub.providers.http import HttpResponse
import json

class ScriptedHttp:
    """Queue of canned responses; recordsevery request."""

    def __init__(self, *responses):
        self.queue, self.calls = list(responses), []

    def push(self, status=200, body=None, text=None):
        raw = text.encode() if text is not None else json.dumps(body or {}).encode()
        self.queue.append(HttpResponse(status, raw))
        return self

    def timeout(self):
        self.queue.append(ProviderUnavailable("timeout"))
        return self
    
    def request(self, method, url, *, headers=None, json_body=None, params=None):
        self.calls.append({"method": method, "url": url, "headers": headers or {}, "json": json_body, params})
        item = self.queue.pop(0)
        if  isinstance(item, Exception):
            raise item
        return item

    
