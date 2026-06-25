from django.contrib import admin
from .models import BoutiqueTenant, Domain

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
