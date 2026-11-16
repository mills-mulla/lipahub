from django.utils.module_loading import  import_string
from .core.errors import ConfigurationError, NoProviderAvailable
from .settings import  get

_instances = {}

def reset():
    _instances.clear()

def register(name, adapter):
    """Inject adapter instance """
    _instances[name] = adapter

def provider_names():
    return list(get("PROVIDERS").keys()) or list(_instances.keys())

def get_adapter(name):
    if name in _instances:
        return _instances[name]

    providers = get("PROVIDERS")

    if name not in providers:
        raise NoProviderAvailable(f"provider {name!r} is not configured")
    
    cfg = dict(providers[name])
    path = cfg.pop("adapter", None)

    if not path:
        raise ConfigurationError(f"provider {name!r} has no 'adapter' path")
    cfg.setdefault("callback_token", get("CALLBACK_TOKEN"))
    cfg.setdefault("allowed_ips", get("CALLBACK_ALLOWED_IPS"))
    _instances[name] = import_string(path)(cfg)
    return _instances[name]

def resolve_provider(*, currency, method, provider=None) -> str:
    """explicit provider when more than 1 matches"""
    if provider:
        if not get_adapter(provider).supports(currency=currency, method=method):
            raise NoProviderAvailable(f"{provider} does not support {method}/{currency}")
        return provider
    matches = [n for n in provider_names() if get_adapter(n).supports(currency=currency, method=method)]
    if len(matches) == 1:
        return matches[0]
    raise NoProviderAvailable(f"{len(matches)} providers support {method}/{currency}; pass provider= explicitly")
