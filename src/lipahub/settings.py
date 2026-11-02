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

def get(name):
    from django.conf import settings
    return {**DEFAULTS, **getattr(settings, "LIPAHUB", {})}[name]