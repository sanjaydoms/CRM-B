from django.apps import AppConfig

class TenantsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tenants'

    def ready(self):
        # The middleware's per-process tenant cache goes stale the moment a
        # tenant row is written or removed. Four call sites (sign-up, the two
        # superadmin views, the Django admin) each remembered to call
        # clear_tenant_cache() by hand; anything that creates a tenant without
        # knowing to -- the test harness above all, where every TenantTestCase
        # reuses the schema name 'test' -- served the previous tenant's row,
        # complete with its owner_email, to the next class's requests. Clearing
        # on the model's own signals covers every writer there will ever be.
        from django.db.models.signals import post_delete, post_save

        from .middleware import clear_tenant_cache
        from .models import BoutiqueTenant

        def _clear(sender, **kwargs):
            clear_tenant_cache()

        post_save.connect(_clear, sender=BoutiqueTenant, weak=False,
                          dispatch_uid='tenants.clear_cache_on_save')
        post_delete.connect(_clear, sender=BoutiqueTenant, weak=False,
                            dispatch_uid='tenants.clear_cache_on_delete')
