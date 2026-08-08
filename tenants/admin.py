from django.contrib import admin
from .models import BoutiqueTenant, DemoRequest, Domain

@admin.register(BoutiqueTenant)
class BoutiqueTenantAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner_email', 'schema_name', 'created_on')
    search_fields = ('name', 'owner_email', 'schema_name')
    readonly_fields = ('created_on',)

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
