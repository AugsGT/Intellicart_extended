from django.apps import AppConfig


class RecommendationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.recommendations"

    def ready(self):
        # Registers the handler that links purchases back to clicked recommendations.
        from apps.recommendations import handlers  # noqa: F401
