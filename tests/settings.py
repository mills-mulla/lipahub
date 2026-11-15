"""Django settings used ONLY by the test-suite and `python manage.py makemigrations lipahub`.

No .env needed: everything has a built-in default. SQLite in memory is the default;
set LIPAHUB_TEST_PG=1 (plus PGHOST/PGUSER/PGPASSWORD/PGDATABASE) to run on Postgres.
"""
import os

SECRET_KEY = "lipahub-tests-only-not-a-secret"
DEBUG = False
USE_TZ = True
TIME_ZONE = "UTC"
ROOT_URLCONF = "tests.urls"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
ALLOWED_HOSTS = ["testserver", "localhost"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "lipahub",
]

if os.getenv("LIPAHUB_TEST_PG"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("PGDATABASE", "lipahub"),
            "USER": os.getenv("PGUSER", "lipahub"),
            "PASSWORD": os.getenv("PGPASSWORD", "lipahub"),
            "HOST": os.getenv("PGHOST", "localhost"),
            "PORT": os.getenv("PGPORT", "5432"),
        }
    }
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"lipahub": {"handlers": ["console"], "level": "WARNING"}},
}

# The test-suite calls lipahub_checks() directly; these only quiet `manage.py check` output.
SILENCED_SYSTEM_CHECKS = [
    "lipahub.W001", "lipahub.W002", "lipahub.W003", "lipahub.W004",
    "lipahub.W005", "lipahub.W006", "lipahub.W007",
]

# Every LipaHub setting, set explicitly. Only the fake provider is configured, so tests that
# omit provider= never see an ambiguous match. Real adapters are tested with scripted HTTP.
LIPAHUB = {
    "PROVIDERS": {"fake": {"adapter": "lipahub.providers.fake.FakeAdapter"}},
    "TASK_RUNNER": "sync",
    "CALLBACK_BASE_URL": "https://example.test",
    "CALLBACK_PATH_PREFIX": "/lipahub",
    "CALLBACK_TOKEN": "tok",
    "CALLBACK_ALLOWED_IPS": [],
    "PENDING_POLL_AFTER_SECONDS": 120,
    "CREATED_REAPER_AFTER_SECONDS": 90,
    "PAYMENT_EXPIRY_MINUTES": 30,
    "RAW_PAYLOAD_RETENTION_DAYS": 30,
    "INBOUND_MERCHANT_ID": 0,
    "OUTBOX_MAX_ATTEMPTS": 10,
}