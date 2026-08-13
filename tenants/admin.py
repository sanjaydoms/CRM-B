"""The tenant registry in Django's own admin.

The product's platform console is the `superadmin` app -- its API and the React
portal at /superadmin. This stays as the back door to the same tables: it needs
no frontend build to be running, no VITE_API_URL, and no CORS, which makes it
what you reach for when the portal itself is what is broken.

Both read the same figures from the same function (superadmin.metrics), because
when this logic was written twice the two surfaces disagreed about what "open
orders" meant.
"""

from django.contrib import admin, messages
from django_tenants.utils import get_public_schema_name

from superadmin.metrics import tenant_metrics

from .middleware import clear_tenant_cache
from .models import BoutiqueTenant, DemoRequest, Domain


def _column(tenant, key):
    """One metric, rendered for a changelist cell.

    None is what superadmin.metrics reports for a schema it could not read; a
    dash says so without pretending the boutique has none of whatever was asked
    for, which is what a 0 here would have claimed.
    """
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

    # schema_name is the tenant's Postgres schema and is set once at sign-up.
    # Editing it here would rename nothing -- the schema would stay where it is
    # and every row in it would become unreachable -- so it is read-only above.

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
        """The single most useful column for spotting a boutique going quiet."""
        value = tenant_metrics(obj)['last_order']
        return value.strftime('%Y-%m-%d') if value else 'never'

    def _set_active(self, request, queryset, active):
        # The public schema is not a boutique -- it is the schema this admin is
        # itself being served from. Suspending it would lock the administrator
        # out of the page they did it on, with no way back in through the
        # product.
        public = queryset.filter(schema_name=get_public_schema_name())
        if public.exists():
            self.message_user(
                request, 'The public schema is not a boutique and was skipped.',
                level=messages.WARNING,
            )
        boutiques = queryset.exclude(schema_name=get_public_schema_name())
        changed = boutiques.update(is_active=active)
        # The middleware holds resolved tenants for a few minutes; drop them so
        # this takes effect now in this process at least (other gunicorn workers
        # catch up at their own TTL -- see the note in middleware.py).
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
    """Where leads live until the superadmin portal reads the same table.

    Status and notes are the only editable fields: everything else was typed by
    a stranger and is evidence of what they actually sent, so it is read-only
    rather than something a careless click can rewrite.
    """

    list_display = ('created_at', 'name', 'boutique', 'email', 'phone', 'status')
    list_filter = ('status', 'created_at')
    search_fields = ('name', 'boutique', 'email', 'phone', 'problem')
    list_editable = ('status',)
    readonly_fields = ('name', 'boutique', 'email', 'phone', 'makes',
                       'orders_per_month', 'people', 'problem', 'ip', 'created_at')
    fields = readonly_fields + ('status', 'notes')
