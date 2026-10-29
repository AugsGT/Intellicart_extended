from django.apps import AppConfig


class InterventionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.interventions"

    def ready(self):
        # Registers the event handlers (cart abandoned, order completed, restocked).
        from apps.interventions import handlers  # noqa: F401
