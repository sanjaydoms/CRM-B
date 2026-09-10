
from django.contrib import admin

from tenants.middleware import clear_platform_cache

from . import audit
from .models import AuditLog, ErrorEvent, FeatureFlag, PlatformSetting


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):

    list_display = ('created_at', 'actor', 'action', 'target', 'boutique', 'ip')
    list_filter = ('action', 'boutique', 'created_at')
    search_fields = ('actor', 'target', 'boutique', 'reason')
    date_hierarchy = 'created_at'

    readonly_fields = tuple(f.name for f in AuditLog._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ErrorEvent)
class ErrorEventAdmin(admin.ModelAdmin):

    list_display = ('last_seen', 'exception_type', 'path', 'boutique',
                    'severity', 'status', 'count')
    list_filter = ('status', 'severity', 'boutique', 'last_seen')
    search_fields = ('exception_type', 'message', 'path', 'fingerprint', 'boutique')
    list_editable = ('status', 'severity')
    date_hierarchy = 'last_seen'

    readonly_fields = ('fingerprint', 'exception_type', 'message', 'traceback',
                       'path', 'method', 'status_code', 'boutique', 'username',
                       'count', 'first_seen', 'last_seen', 'resolved_by',
                       'resolved_at')
    fields = readonly_fields + ('severity', 'status', 'notes')

    def has_add_permission(self, request):
        return False


@admin.register(FeatureFlag)
class FeatureFlagAdmin(admin.ModelAdmin):
    list_display = ('key', 'enabled', 'rollout_percent', 'enabled_for',
                    'modified_by', 'updated_at')
    list_filter = ('enabled',)
    search_fields = ('key', 'description')
    readonly_fields = ('created_by', 'modified_by', 'created_at', 'updated_at')

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user.username
        obj.modified_by = request.user.username
        super().save_model(request, obj, form, change)
        audit.record(request, 'flag.change', target=obj.key,
                     after={'enabled': obj.enabled,
                            'rollout_percent': obj.rollout_percent,
                            'enabled_for': obj.enabled_for},
                     reason='changed in Django admin')


@admin.register(PlatformSetting)
class PlatformSettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'value', 'updated_by', 'updated_at')
    search_fields = ('key', 'description')
    readonly_fields = ('updated_by', 'updated_at')

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user.username
        super().save_model(request, obj, form, change)
        audit.record(request, 'setting.change', target=obj.key,
                     after={'value': obj.value},
                     reason='changed in Django admin')
        clear_platform_cache()
