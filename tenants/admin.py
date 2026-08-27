
from django.contrib import admin, messages
from django_tenants.utils import get_public_schema_name

from superadmin.metrics import tenant_metrics

from .middleware import clear_tenant_cache
from .models import BoutiqueTenant, DemoRequest, Domain


def _column(tenant, key):
    value = tenant_metrics(tenant)[key]
    return '-' if value is None else value


@admin.register(BoutiqueTenant)
class BoutiqueTenantAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner_email', 'schema_name', 'is_active', 'created_on',
                    'staff_count', 'customer_count', 'order_count', 'open_order_count',
                    'revenue', 'last_order')
    list_filter = ('is_active', 'created_on')
    search_fields = ('name', 'owner_email', 'schema_name')
    readonly_fields = ('created_on', 'schema_name')
    actions = ('suspend', 'reactivate')


    @admin.display(description='Staff')
    def staff_count(self, obj):
        return _column(obj, 'staff')

    @admin.display(description='Customers')
    def customer_count(self, obj):
        return _column(obj, 'customers')

    @admin.display(description='Orders')
    def order_count(self, obj):
        return _column(obj, 'orders')

    @admin.display(description='Open')
    def open_order_count(self, obj):
        return _column(obj, 'open_orders')

    @admin.display(description='Revenue')
    def revenue(self, obj):
        value = tenant_metrics(obj)['revenue']
        return '-' if value is None else f'{value:,.0f}'

    @admin.display(description='Last order')
    def last_order(self, obj):
        value = tenant_metrics(obj)['last_order']
        return value.strftime('%Y-%m-%d') if value else 'never'

    def _set_active(self, request, queryset, active):
        public = queryset.filter(schema_name=get_public_schema_name())
        if public.exists():
            self.message_user(
                request, 'The public schema is not a boutique and was skipped.',
                level=messages.WARNING,
            )
        boutiques = queryset.exclude(schema_name=get_public_schema_name())
        affected = list(boutiques.values_list('schema_name', flat=True))
        changed = boutiques.update(is_active=active)

        from superadmin import audit
        for schema_name in affected:
            audit.record(
                request,
                'boutique.reactivate' if active else 'boutique.suspend',
                target=schema_name, boutique=schema_name,
                before={'is_active': not active}, after={'is_active': active},
                reason='Changed in the Django admin (bulk action).',
            )
        clear_tenant_cache()
        self.message_user(
            request,
            f"{changed} boutique(s) {'reactivated' if active else 'suspended'}.",
        )

    @admin.action(description='Suspend selected boutiques (blocks sign-in and API)')
    def suspend(self, request, queryset):
        self._set_active(request, queryset, False)

    @admin.action(description='Reactivate selected boutiques')
    def reactivate(self, request, queryset):
        self._set_active(request, queryset, True)


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ('domain', 'tenant', 'is_primary')
    search_fields = ('domain', 'tenant__name')
    list_filter = ('is_primary',)


@admin.register(DemoRequest)
class DemoRequestAdmin(admin.ModelAdmin):

    list_display = ('created_at', 'name', 'boutique', 'email', 'phone', 'status')
    list_filter = ('status', 'created_at')
    search_fields = ('name', 'boutique', 'email', 'phone', 'problem')
    list_editable = ('status',)
    readonly_fields = ('name', 'boutique', 'email', 'phone', 'makes',
                       'orders_per_month', 'people', 'problem', 'ip', 'created_at')
    fields = readonly_fields + ('status', 'notes')
