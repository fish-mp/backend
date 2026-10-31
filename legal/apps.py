from django.apps import AppConfig


class LegalConfig(AppConfig):
    name = 'legal'

    def ready(self):
        from . import checks
