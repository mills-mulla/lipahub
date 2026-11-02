"""Errors shared by the core,the services and every adapter"""

class LipahubError(Exception):
    """BAse class for every error LipaHub raises on purpose"""

class InvalidAmount(LipahubError, ValueError):
    """Not a whole number of minor units or not payable in whole units"""

class InvalidPhoneNumber(LipahubError, ValueError):
    """A phone number cannot be normalised to E.164."""

class IllegalTransition(LipahubError):
    """A transition is not allowed by the state machine"""
    def __init__(self, from_status, to_status, reason=""):
        self.from_status, self.to_status = str(from_status), str(to_status)
        msg = f"illegal transiton {self.from_status} -> {self.to_status}"

        super().__init__(msg + (f": {reason}" if reason else ""))

class ConfigurationError(LipahubError):
    """Settings or config provided is missing or wrong"""

class NoProviderAvailable(LipahubError):
    """No provider supports the request or several do and none was named"""

class IdempotencyConflict(LipahubError):
    """A request with the same idempotency key was already made with different parameters"""

class NotSupported(LipahubError):
    """The requested operation is not supported by the provider or the adapter"""

class ProviderRejected(LipahubError):
    """The provider rejected the request, usually due to invalid parameters.The payment fails."""
    def __init__(self, message="rejected by provider", code="provider_error", raw=None):
        super().__init__(message)
        self.message, self.code, self.raw = message, code, raw or {}

class ProviderUnavailable(LipahubError):
    """The provider is not available, usually due to a network or service outage.the payment ststus remains pending.Never retry blindly"""
    def __init__(self, message="provider unavailable", raw=None):
        super().__init__(message)
        self.message, self.raw = message, raw or {}

class InvalidWebhook(LipahubError):
    """Failed authentication or parsing.Never touches a payment. "status" is the HTTP reply."""
    def __init__(self, message="invalid webhook", status=400):
        super().__init__(message)
        self.message, self.status = message, status 