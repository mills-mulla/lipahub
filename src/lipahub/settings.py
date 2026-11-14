# DEFAULTS = {
#     "PROVIDERS": {},
#     "TASK_RUNNER": "sync",
#     "CALLBACK_BASE_URL": "",
#     "CALLBACK_PATH_PREFIX: "/lipahub",
#     "CALLBACK_TOKEN": "",
#     "CALLBACK_ALLOWED_IPS": [],
#     "PENDING_POLL_AFTER_SECONDS": 120,
#     "CREATED_REAPER_AFTER_SECONDS": 90,
#     "PAYMENT_EXPIRY_MINUTES": 30,
#     "RAW_PAYLOAD_RETENTION_DAYS": 30,
#     "INBOUND_MERCHANT_ID": 0,
#     "OUTBOUND_MERCHANT_ID": 10,
# }

# def get(name):
#     from django.conf import settings
#     return {**DEFAULTS, **getattr(settings, "LIPAHUB", {})}[name]

import os

SECRET_KEY = "test"
DEBUG = False
USE_TZ = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "lipahub",
]

ROOT_URLCONF = "test.urls"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SILENCED_SYSTEM_CKECKS = ["lipahub.W001, lipahub.W002, lipahub.W003, lipahub.W004"]

if os.getenv("DATABASE_URL"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["DB_NAME"],
            "USER": os.environ["DB_USER"],
            "PASSWORD": os.environ["DB_PASSWORD"],
            "HOST": os.environ["DB_HOST"],
            "PORT": os.environ["DB_PORT"],
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }


LIPAHUB = {
    "PROVIDERS": {"fake": {"adapter": "lipahub.providers.fake.FakeAdapter"}},
    "CALLBACK_BASE_URL": "https://example.test",
    "CALLBACK_TOKEN": "tok"
}