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