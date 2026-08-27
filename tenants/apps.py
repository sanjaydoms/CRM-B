from django.apps import AppConfig

class TenantsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tenants'

    def ready(self):
        from django.db.models.signals import post_delete, post_save

        from .middleware import clear_tenant_cache
        from .models import BoutiqueTenant

        def _clear(sender, **kwargs):
            clear_tenant_cache()

        post_save.connect(_clear, sender=BoutiqueTenant, weak=False,
                          dispatch_uid='tenants.clear_cache_on_save')
        post_delete.connect(_clear, sender=BoutiqueTenant, weak=False,
                            dispatch_uid='tenants.clear_cache_on_delete')
