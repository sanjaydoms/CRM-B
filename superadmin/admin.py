"""The console's own tables in Django's admin.

Same role as tenants/admin.py: the React portal at /superadmin is the product,
and this is the back door to the same rows -- no frontend build, no
VITE_API_URL, no CORS. It is what you reach for when the console itself is what
is broken, which is exactly when the error feed and the audit trail matter most.

The two records are treated differently on purpose. AuditLog is append-only and
is registered read-only in every direction. ErrorEvent is a worklist: its
captured fields are evidence and are read-only, while triage (status, severity,
notes) is the whole reason to open it.
"""

from django.contrib import admin

# Module level is safe in this direction: superadmin already imports tenants
# (users.py imports tenants.models, tenants/admin.py imports superadmin.metrics),
# and tenants/middleware.py imports nothing from superadmin at module level --
# its own PlatformSetting import is function-local for exactly that reason.
from tenants.middleware import clear_platform_cache

from . import audit
from .models import AuditLog, ErrorEvent, FeatureFlag, PlatformSetting


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Append-only, and enforced here as far as the admin can enforce it.

    The API exposes no write route at all; this is the other surface that could
    have created one, so add and delete are refused outright. Change is left
    enabled only so the detail page renders -- with every field read-only there
    is nothing on it to save. Postgres can be told to refuse UPDATE and DELETE
    on the table itself; that is a deployment step and it is written up in the
    README rather than imposed by a migration.
    """

    list_display = ('created_at', 'actor', 'action', 'target', 'boutique', 'ip')
    list_filter = ('action', 'boutique', 'created_at')
    search_fields = ('actor', 'target', 'boutique', 'reason')
    date_hierarchy = 'created_at'

    # Derived rather than listed. A column added to AuditLog later must be
    # read-only by default; spelling the list out here would make it editable
    # by omission, which is the one mistake this table cannot afford.
    readonly_fields = tuple(f.name for f in AuditLog._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ErrorEvent)
class ErrorEventAdmin(admin.ModelAdmin):
    """The crash feed, triageable but not forgeable.

    No add permission: rows here come from the exception handler, and one typed
    by hand is a fiction in the middle of evidence. Delete is allowed, because
    unlike the audit trail this is a worklist and pruning resolved noise from it
    is legitimate housekeeping.
    """

    list_display = ('last_seen', 'exception_type', 'path', 'boutique',
                    'severity', 'status', 'count')
    list_filter = ('status', 'severity', 'boutique', 'last_seen')
    search_fields = ('exception_type', 'message', 'path', 'fingerprint', 'boutique')
    list_editable = ('status', 'severity')
    date_hierarchy = 'last_seen'

    # Everything the handler captured is evidence. Only the triage fields below
    # are editable, and `fields` is ordered so the crash reads top to bottom.
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
        """Stamp the editor and audit the change.

        Both for the same reason: a flag flipped through the back door must not
        look like a flag nobody touched. `modified_by` would otherwise keep
        whoever set it last through the API, and the console's history page
        reads AuditLog rather than django_admin_log, so without this line the
        change happened as far as Django is concerned and never happened as far
        as the product is concerned.
        """
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
        # Same reasoning as FeatureFlagAdmin.save_model above.
        obj.updated_by = request.user.username
        super().save_model(request, obj, form, change)
        audit.record(request, 'setting.change', target=obj.key,
                     after={'value': obj.value},
                     reason='changed in Django admin')
        # This is the only production writer of PlatformSetting, and
        # tenants.middleware._maintenance_mode caches the row for 300s per
        # worker. Without this line, turning maintenance mode on or off in the
        # admin takes effect at the TTL rather than at the click -- the save
        # page says it is done and the platform disagrees for five minutes.
        #
        # ponytail: clears THIS worker only, and gunicorn.conf.py runs 2 of
        # them, so the other worker keeps its stale answer for up to 300s --
        # roughly half of traffic. See the ceiling written up in
        # tenants/middleware.py _maintenance_mode.
        clear_platform_cache()
