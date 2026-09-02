from django.apps import AppConfig


class CrmApiConfig(AppConfig):
    name = 'crm_api'

    def ready(self):
        # Registers the post_save receiver that turns a Notification row into a
        # push. Imported here rather than at module level because it imports
        # models, which are not loaded when this file is.
        from crm_api import push  # noqa: F401
