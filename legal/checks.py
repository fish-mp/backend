from django.core.checks import Error, register
from django.core.exceptions import ImproperlyConfigured
from .catalog import catalog


@register()
def legal_documents_check(app_configs, **kwargs):
    try:
        catalog()
    except ImproperlyConfigured as exc:
        return [Error(str(exc), id='legal.E001')]
    return []
