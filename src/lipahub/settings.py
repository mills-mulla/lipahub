import os
from django.core.exceptions import ImproperlyConfigured

SECRET_KEY = "test"
DEBUG = False
USE_TZ = True

DEFAULTS = {
    "PROVIDERS": {},
    "TASK_RUNNER": "sync",
    "CALLBACK_BASE_URL": "",
    "CALLBACK_PATH_PREFIX: "/lipahub",
    "CALLBACK_TOKEN": "",
    "CALLBACK_ALLOWED_IPS": [],
    "PENDING_POLL_AFTER_SECONDS": 120,
    "CREATED_REAPER_AFTER_SECONDS": 90,
    "PAYMENT_EXPIRY_MINUTES": 30,
    "RAW_PAYLOAD_RETENTION_DAYS": 30,
    "INBOUND_MERCHANT_ID": 0,
    "OUTBOUND_MERCHANT_ID": 10,
}

RUNNERS = ("sync", "celery")
POSITIVE_INTS = (
    "PENDING_POLL_AFTER_SECONDS", "CREATED_REAPER_AFTER_SECONDS", "PAYMENT_EXPIRY_MINUTES",
    "RAW_PAYLOAD_RETENTION_DAYS", "OUTBOX_MAX_ATTEMPTS",
)
MIN_TOKEN_LENGTH = 24

def env(name, default=""):
    """
    read a secret from the environment or use default
    """
    return os.environ.get(name, default)

def all_settings() -> dict:
    from django.conf import settings

   return {**DEFAULTS, **(getattr(settings, "LIPAHUB", None) or {})}


def get(name):
    cfg = all_settings()
    if name not in cfg:
        raise ImproperlyConfigured(f"missing lipahub setting {name!r}")
    return cfg[name]

def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)

def validate(user_cfg=None):
    from django.conf import settings as dj

    user = user_cfg if user_cfg  is not None else  (getattr(dj, "LIPAHUB", None) or {})
    cfg = {**DEFAULTS, **user}
    out = []

    for key in user:
        if key not in DEFAULTS:
            out.append(("error", "lipahub.E001",  f"Unknown LIPAHUB setting {key!r} (typo?)."))
        if cfg["TASK_RUNNER"] not in RUNNERS:
            out.append(("error", "lipahub.E002", f"LIPAHUB.TASK_RUNNER {cfg['TASK_RUNNER']!r} is not valid. Use one of {RUNNERS}"))
        if key in POSITIVE_INTS:
            if not _is_int(cfg[key]) or cfg[key] < 0:
                out.append(("error", "lipahub.E003", f"LIPAHUB setting {key!r} must be a positive integer"))
        if not _is_int(cfg["INBOUND_MERCHANT_ID"] or cfg["INBOUND_MERCHANT_ID"] < 0:
            out.append(("error", "lipahub.E003", f"LIPAHUB setting INBOUND_MERCHANT_ID must be integers >=0"))
        
        providers = cfg["PROVIDERS"]
        if not isinstance(providers, dict):
            out.append(("error", "lipahub.E004, "LIPAHUB.PROVIDERS must be a dictionary"))
        else:
            for name, pc in providers.items():
                if not isinstance(pc, dict) or not isinstance(pc.get("adapter"), str):
                    out.append(("error", "lipahub.E005", f"provider {name!r} adapter must be a string"))
        if not isinstance(cfg["CALLBACK_ALLOWED_IPS"], (list, tuple)):
            out.append(("error", "lipahub.E006", "LIPAHUB.CALLBACK_ALLOWED_IPS must be a list or tuple"))
        prefix = cfg["CALLBACK_PATH_PREFIX"]
        if prefix and not str(prefix).startswith("/"):
            out.append(("error", "lipahub.E007", "LIPAHUB.CALLBACK_PATH_PREFIX must be empty or start with a forward slash"))
        
        base = str(cfg["CALLBACK_BASE_URL"])
        if base and not base.startswith(("http://", "https://")):
            out.append(("error", "lipahub.E008", "LIPAHUB.CALLBACK_BASE_URL must be empty or start with http:// or https://"))
        elif base.startswith("http://") and not dj.DEBUG:
            out.append(("warning", "lipahub.W005", "LIPAHUB.CALLBACK_BASE_URL is using HTTP - use HTTPS in production!"))
        if not base and isinstance(providers, dict) and providers:
            out.append(("warning", "lipahub.W007", "LIPAHUB.CALLBACK_BASE_URL is not set - webhook callbacks may not work"))
        
        token = str(cfg["CALLBACK_TOKEN"])
        if token and len(token) < MIN_TOKEN_LENGTH and not dj.DEBUG:
            out.append(("warning", "lipahub.W006", f"LIPAHUB.CALLBACK_TOKEN must be at least {MIN_TOKEN_LENGTH} characters"))

    return out):


# SECRET_KEY = "test"
# DEBUG = False
# USE_TZ = True

# INSTALLED_APPS = [
#     "django.contrib.contenttypes",
#     "django.contrib.auth",
#     "lipahub",
# ]

# ROOT_URLCONF = "test.urls"
# DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
# SILENCED_SYSTEM_CKECKS = ["lipahub.W001, lipahub.W002, lipahub.W003, lipahub.W004"]

# if os.getenv("DATABASE_URL"):
#     DATABASES = {
#         "default": {
#             "ENGINE": "django.db.backends.postgresql",
#             "NAME": os.environ["DB_NAME"],
#             "USER": os.environ["DB_USER"],
#             "PASSWORD": os.environ["DB_PASSWORD"],
#             "HOST": os.environ["DB_HOST"],
#             "PORT": os.environ["DB_PORT"],
#         }
#     }
# else:
#     DATABASES = {
#         "default": {
#             "ENGINE": "django.db.backends.sqlite3",
#             "NAME": ":memory:",
#         }
#     }


# LIPAHUB = {
#     "PROVIDERS": {"fake": {"adapter": "lipahub.providers.fake.FakeAdapter"}},
#     "CALLBACK_BASE_URL": "https://example.test",
#     "CALLBACK_TOKEN": "tok"
# }