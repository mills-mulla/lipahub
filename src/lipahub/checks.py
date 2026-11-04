from django.conf import settings
from django.core.checks import warning, register

from .settings import get

@register()
def lipahub_checks(app_configs, **kwargs):
    out = []
    db = settings.DATABASES.get("default", {})
    engine = db.get ("ENGINE", "")
    if not engine.endswith(("postgresql","mysql")):
        out.append(warning("Lipahub needs PostgreSQL or MySQL", id="lipahub.W001"))
    if db.get("ATOMIC_REQUESTS"):
        out.append(warning("ATOMIC_REQUESTS=True wraps webhook handling in one transaction; a failure rolls back to the stored event", id="lipahub.W002"))
    cache_backend = settings.CACHES.get("default", {}).get("BACKEND", "")
    if not settings.DEBUG and ("locmem" in cache_backend or "dummy" in cache_backend):
        out.append(warning("use shared cache otherwise  provider tokens are cached per worker", id="lipahub.W003"))
    if not get("CALLBACK_TOKEN"):
        out.append(warning("LIPAHUB['CALLBACK_TOKEN'] is not set; webhook callbacks will be refused", id="lipahub.W004"))
    return out
    
