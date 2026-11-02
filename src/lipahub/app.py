from django.apps import AppConfig

class LipaHubConfig(AppConfig):
    name = "lipahub"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import checks, signals  # noqa: F401