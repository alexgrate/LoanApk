from django.apps import AppConfig


class LoansConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'loans'

    def ready(self):
        # Registers the email normaliser. Importing here rather than at module
        # level is Django's documented way to connect signals.
        from . import signals  # noqa: F401
