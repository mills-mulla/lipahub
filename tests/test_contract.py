import pytest

from src.lipahub.core.errors import InvalidWebhook, ProviderUnavailable
from src.lipahub.core.types import Capabilities, InitiateResult, PaymentData

TOKEN = "tok"

class AdapterContract:
    """ subclass and implement make (http) -> adapter, plus the payment()/good_webhook() helpers. """

    def make(self, http=None):
        raise NotImplementedError

    def payment(self, **kw):
        raise NotImplementedError
    
    def good_webhook(self):
        """-> (headers dict, body bytes) that the adapter accepts with TOKEN"""
        raise NotImplementedError

    def accept_initiate_http(self, http):
        """
        queue the http replies for  one succesful initiate()
        """
        raise NotImplementedError

    
    def test_shape(self):
        a = self.make()
        assert isinstance(a.name, str) and isinstance(a.capabilities, Capabilities)

    def test_webhook_rejects_wrong_token(self):
        headers, body = self.good_webhook()
        with pytest.raises(InvalidWebhook) as e:
            self.make().parse_webhook(headers, body, "WRONG")
        assert e.value.status == 403

    def test_initiate_timeout_is_unknown_outcome(self):
        from tests.providers.scripted_http import ScriptedHttp

        http = ScriptedHttp()
        """ a timeout on the first call the adaptermakes must surface as 'unknown'"""
        http.timeout()
        with pytest.raises(ProviderUnavailable):
            self.make(http).initiate(self.payment())

    def test_initiate_makes_one_attempt_only(self):
        from tests.providers.scripted_http import ScriptedHttp

        http = ScriptedHttp()
        http.timeout()
        try:
            self.make(http).initiate(self.payment())
        except ProviderUnavailable:
            pass
        assert len(http.calls) == 1 # no retries inside initiate()       

    




    