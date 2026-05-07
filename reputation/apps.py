from django.apps import AppConfig


class ReputationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "reputation"
    verbose_name = "Global Reputation (Blacklist/Whitelist)"

    def ready(self):
        from reputation.signals import register_signals
        register_signals()
