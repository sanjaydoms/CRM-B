import time

from django.db import connection
from django.http import JsonResponse
from django_tenants.middleware.main import TenantMainMiddleware
from django_tenants.utils import get_tenant_model, get_public_schema_name, get_tenant_domain_model, schema_context

from core.modules import ALWAYS_ON, MODULES, is_enabled, module_for_path

# Resolving the tenant is the first thing every request does, and it used to cost
# a database round trip before any application query could start -- on a hosted
# database that is tens of milliseconds added to literally every call. Tenants
# are created at sign-up and then essentially never change, so they are cached in
# process for a short window. The TTL is what keeps a newly created or renamed
# tenant from being invisible to already-running workers; it does not need to be
# long, because the saving is per-request rather than per-window.
_TENANT_CACHE_TTL = 300
_tenant_cache = {}

#: Requests under this prefix belong to the platform console (superadmin/) and
#: are pinned to the public schema below, skipping tenant resolution entirely.
#: Must match where superadmin.urls is mounted in boutique_crm/urls.py.
SUPERADMIN_PREFIX = '/api/superadmin/'


def _get_tenant_by_schema(tenant_model, schema_name):
    """Return the tenant for a schema, or None, going to the database at most
    once per TTL per worker."""
    hit = _tenant_cache.get(schema_name)
    now = time.monotonic()
    if hit is not None and hit[1] > now:
        return hit[0]
    try:
        tenant = tenant_model.objects.get(schema_name=schema_name)
    except tenant_model.DoesNotExist:
        tenant = None
    # Negative results are cached too, so a client looping on a stale tenant id
    # cannot turn a 400 into a query per request.
    _tenant_cache[schema_name] = (tenant, now + _TENANT_CACHE_TTL)
    return tenant


def clear_tenant_cache():
    """Drop the cached tenants. Call after creating or renaming a tenant in the
    same process so the change is visible immediately rather than at the TTL."""
    _tenant_cache.clear()


#: Maintenance mode is read on *every* request, so it gets the same treatment as
#: the tenant above: at most one query per TTL per worker. A settings row that is
#: false 99.99% of the time is not worth a round trip per call.
_platform_cache = {}


def clear_platform_cache():
    """Drop the cached platform settings. Call after writing one in the same
    process -- flipping maintenance mode in the console otherwise takes effect
    at the TTL rather than at the click."""
    _platform_cache.clear()


def _maintenance_mode():
    """The stored maintenance_mode dict, or None when it is off or unset.

    PlatformSetting is imported inside the function on purpose: `superadmin`
    imports `tenants`, so a module-level import here closes the cycle and
    Django fails to start.

    A missing table means a database that has not been migrated yet -- during
    the very first `migrate`, or in a test database being built -- and the
    honest reading of "the maintenance switch does not exist" is that
    maintenance is off. Refusing every request because the table that says
    whether to refuse is absent would make a fresh deploy unbootable.

    ponytail: this cache is per PROCESS and clear_platform_cache() only clears
    the worker that calls it. gunicorn.conf.py runs 2 workers, so the writer in
    superadmin/admin.py clears one of them and the other keeps answering from
    its stale copy for up to _TENANT_CACHE_TTL. Turning maintenance ON is
    merely late; turning it OFF is the bad direction -- roughly half of traffic
    keeps getting 503 for another 300 seconds after the administrator has
    switched it off and been told it worked. The fix is a shared cache (the
    Django cache framework backed by whatever the deployment already runs), or
    dropping the cache and reading the row every request and accepting one
    indexed single-row SELECT per call. Same shape as the tenant-suspension lag
    noted in process_request below, but with a worse failure direction.
    """
    hit = _platform_cache.get('maintenance_mode')
    now = time.monotonic()
    if hit is not None and hit[1] > now:
        return hit[0]

    value = None
    try:
        from superadmin.models import PlatformSetting
        # The row is in public and the connection still carries whatever schema
        # the previous request left on it (CONN_MAX_AGE), so the schema is named
        # rather than assumed.
        with schema_context(get_public_schema_name()):
            row = PlatformSetting.objects.filter(key='maintenance_mode').first()
        if row and isinstance(row.value, dict) and row.value.get('enabled'):
            value = row.value
    except Exception:
        value = None

    # The "off" answer is cached too -- it is the one that is true almost always,
    # and leaving it uncached would mean the query per request this exists to avoid.
    _platform_cache['maintenance_mode'] = (value, now + _TENANT_CACHE_TTL)
    return value


class TenantHeaderMiddleware(TenantMainMiddleware):
    def process_request(self, request):
        # 0. The platform console is not a tenant and must never resolve to one.
        #
        # Three separate reasons, any one of which is enough:
        #
        #   * Correctness. The console's superuser and its token live in the
        #     public schema. Let a tenant be resolved -- from a stale
        #     X-Tenant-ID left in the browser, or from a hostname that happens
        #     to match a Domain row -- and authentication reads that boutique's
        #     User and authtoken tables instead, so the administrator is simply
        #     not found and every call 401s. IsPlatformAdmin also refuses any
        #     non-public schema, which turns that into a flat wall of 403s.
        #   * Cost. Step 2 below walks *every* tenant schema hunting for the
        #     token, one query per boutique, and a public-schema token is in
        #     none of them -- so the console would pay the full sweep on every
        #     request before falling through to public anyway.
        #   * Availability. Step 4 refuses a suspended tenant. Suspending the
        #     wrong boutique would otherwise be unfixable through the console
        #     that did it, if the console resolved to that tenant.
        #
        # Pinned before anything is read, so no later branch can undo it.
        if request.path.startswith(SUPERADMIN_PREFIX):
            connection.set_schema_to_public()
            return None

        # 0b. Maintenance mode, before any tenant is resolved -- there is no
        # point pricing a tenant lookup for a request that is about to be
        # refused, and the switch is platform-wide so it does not need one.
        #
        # ALWAYS_ON stays reachable, and the entry that matters is
        # '/api/superadmin/': a maintenance switch that locks out the console
        # that flips it can only be turned off by a database client, which is
        # the wrong tool to reach for during an outage. (The pin above has
        # already returned for that prefix; it is in ALWAYS_ON so the exemption
        # survives someone reordering these blocks.) '/api/auth/' and '/admin/'
        # come along for the ride, so an administrator can still sign in.
        #
        # 503 rather than 403: this is temporary and about the platform, not
        # about who is asking. Clients and proxies treat the two very
        # differently, and only one of them is worth retrying.
        maintenance = _maintenance_mode()
        if maintenance and not any(request.path.startswith(p) for p in ALWAYS_ON):
            return JsonResponse(
                {"error": maintenance.get('message')
                          or "The platform is down for maintenance. Please try again shortly.",
                 "maintenance": True},
                status=503,
            )

        # 1. First, check request headers for X-Tenant-ID
        tenant_schema = request.headers.get("X-Tenant-ID")

        tenant_model = get_tenant_model()
        public_schema_name = get_public_schema_name()

        tenant = None
        if tenant_schema and tenant_schema != 'public':
            tenant = _get_tenant_by_schema(tenant_model, tenant_schema)
            if tenant is None:
                # Falling through to the public schema here used to surface as a
                # raw "relation crm_api_customer does not exist" 500, because the
                # business tables only exist inside tenant schemas.
                return JsonResponse(
                    {"error": f"Unknown tenant '{tenant_schema}'."}, status=400
                )

        # 2. If not resolved via header, fallback to Authorization Token context search.
        #
        # This walks every tenant schema looking for the token, so it costs a query
        # per boutique on the account -- fine at three tenants, a scaling wall at
        # three hundred. It only runs for clients that send a token without an
        # X-Tenant-ID (the frontend always sends both), so it stays as the safety
        # net it was, but it must not become the normal path.
        if not tenant:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Token "):
                token_key = auth_header.split(" ")[1]
                for t in tenant_model.objects.exclude(schema_name='public'):
                    with schema_context(t.schema_name):
                        from rest_framework.authtoken.models import Token
                        if Token.objects.filter(key=token_key).exists():
                            tenant = t
                            break

        # 3. If not resolved via token, fallback to hostname (default django-tenants behavior)
        if not tenant:
            hostname = self.hostname_from_request(request)
            domain_model = get_tenant_domain_model()
            try:
                domain = domain_model.objects.select_related('tenant').get(domain=hostname)
                tenant = domain.tenant
            except domain_model.DoesNotExist:
                # Fallback to public tenant
                tenant = _get_tenant_by_schema(tenant_model, public_schema_name)

        # A suspended boutique is refused here, after every resolution path
        # above has had its turn, because this is the single point where a
        # tenant becomes the connection's schema. Guarding each path separately
        # would leave the next one added unguarded.
        #
        # 403 rather than 400: the tenant exists and the caller's token is
        # genuine, and the frontend already treats 400 from here as "bad tenant
        # id, retry" while 403 surfaces the message.
        #
        # Note the tenant cache above: a suspension applied in the admin is
        # visible to other worker processes only once their cached copy expires,
        # so it takes effect within _TENANT_CACHE_TTL rather than instantly.
        # ponytail: TTL-delayed suspension, adequate for billing and abuse.
        # Needs a shared cache invalidation only if it ever has to be immediate.
        if tenant is not None and not getattr(tenant, 'is_active', True):
            return JsonResponse(
                {"error": "This boutique's access has been suspended. "
                          "Please contact support."},
                status=403,
            )

        # A module the platform administrator has withheld from this boutique.
        #
        # Enforced here, and not in a permission class, because a permission
        # class is not a chokepoint: 21 views declare their own
        # permission_classes and never consult RolePermission at all, so a
        # DRF-level gate would hold on some endpoints and be silently absent on
        # the others -- and absent on every view added afterwards that forgets.
        # This middleware is MIDDLEWARE[1] and every request goes through it.
        #
        # module_for_path() returns None for an always-on route and for any path
        # no module claims. None means NOT GOVERNED and is always allowed: deny
        # on None and the first casualty is /api/auth/login/, followed by every
        # URL added before someone remembers to update core/modules.py.
        #
        # Same cache lag as the suspension check: the tenant carrying
        # enabled_modules is the cached copy, so a switch flipped in the console
        # reaches other workers within _TENANT_CACHE_TTL rather than at once.
        if tenant is not None:
            module = module_for_path(request.path)
            if module is not None and not is_enabled(tenant.enabled_modules, module):
                # Names the module and says it is a per-boutique setting, so this
                # is not mistaken for the suspension 403 (whole boutique, billing)
                # or a role denial (this user, their permissions). Three different
                # causes that used to be one indistinguishable "Forbidden".
                return JsonResponse(
                    {"error": f"The {MODULES[module][0]} module is switched off for "
                              f"this boutique. Contact platform support to enable it.",
                     "module": module},
                    status=403,
                )

        if tenant:
            tenant.domain_url = request.get_host()
            request.tenant = tenant
            connection.set_tenant(request.tenant)
            self.setup_url_routing(request)
        else:
            connection.set_schema_to_public()
