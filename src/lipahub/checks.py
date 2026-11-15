from django.conf import settings
from django.core.checks import Error, Warning, register

from .settings import get, validate

@register()
def lipahub_checks(app_configs, **kwargs):
    out = []
    for level, check_id, msg in validate():
        out.append((Error if level == "error" else Warning)(msg, id=check_id))
        
    db = settings.DATABASES.get("default", {})
    engine = db.get ("ENGINE", "")
    if not engine.endswith(("postgresql","mysql")):
        out.append(Warning("Lipahub needs PostgreSQL or MySQL", id="lipahub.W001"))
    if db.get("ATOMIC_REQUESTS"):
        out.append(Warning("ATOMIC_REQUESTS=True wraps webhook handling in one transaction; a failure rolls back to the stored event", id="lipahub.W002"))
    cache_backend = settings.CACHES.get("default", {}).get("BACKEND", "")
    if not settings.DEBUG and ("locmem" in cache_backend or "dummy" in cache_backend):
        out.append(Warning("use shared cache otherwise  provider tokens are cached per worker", id="lipahub.W003"))
    if not get("CALLBACK_TOKEN"):
        out.append(Warning("LIPAHUB['CALLBACK_TOKEN'] is not set; webhook callbacks will be refused", id="lipahub.W004"))
    return out
    
