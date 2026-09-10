from django.apps import AppConfig


class CoreConfig(AppConfig):
    """The only reason `core` is an installed app.

    core owns no models, so listing it in SHARED_APPS adds no migration to
    either schema set. It is listed so that ready() runs, and ready() runs so
    that core.checks registers -- a check that is never imported never fails a
    deploy, which is the whole point of it. The alternative, hanging the import
    off some other app's AppConfig, puts core's guards in a file named after
    something else.
    """

    name = 'core'

    def ready(self):
        from . import checks  # noqa: F401  registers the system checks
