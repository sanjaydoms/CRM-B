import logging
import time

from django.db import connection
from django.utils import timezone
from django.http import JsonResponse
from django_tenants.middleware.main import TenantMainMiddleware
from django_tenants.utils import get_tenant_model, get_public_schema_name, get_tenant_domain_model, schema_context

from core.modules import ALWAYS_ON, MODULES, is_enabled, module_for_path

logger = logging.getLogger(__name__)


def _schema_exists(schema_name):
    """Whether `schema_name` is a real Postgres schema.

    Delegates to superadmin.schemas, which already owns this question and its
    cache, rather than carrying a second copy of the rule. Imported inside the
    function because `superadmin` imports `tenants`, so a module-level import
    closes the cycle and Django fails to start -- the same reason
    _maintenance_mode() below defers its own import.
    """
    from superadmin.schemas import schema_exists
    return schema_exists(schema_name)

# Resolving the tenant is the first thing every request does, and it used to cost
# a database round trip before any application query could start -- on a hosted
# database that is tens of milliseconds added to literally every call. Tenants
# are created at sign-up and then essentially never change, so they are cached in
# process for a short window. The TTL is what keeps a newly created or renamed
# tenant from being invisible to already-running workers; it does not need to be
# long, because the saving is per-request rather than per-window.
#
# This caches a boutique's IDENTITY only. Whether it is still allowed in --
# is_active and enabled_modules -- is read from the database on every request by
# _control_state below, because a security control served from a per-worker
# cache is not a control. Do not reintroduce either column here.
_TENANT_CACHE_TTL = 300
_tenant_cache = {}

#: Requests under this prefix belong to the platform console (superadmin/) and
#: are pinned to the public schema below, skipping tenant resolution entirely.
#: Must match where superadmin.urls is mounted in boutique_crm/urls.py.
SUPERADMIN_PREFIX = '/api/superadmin/'

#: Every path that is PLATFORM surface and must therefore run in the public
#: schema, whatever the request asks for.
#:
#: '/admin/' is here because leaving it out was a privilege escalation, measured
#: end to end:
#:
#:   * `tenants` and `superadmin` are SHARED_APPS only, so tenants_boutiquetenant
#:     and superadmin_auditlog exist ONLY in public -- but a tenant search_path is
#:     `'<tenant>', public`, so they still resolve from inside a boutique.
#:   * `django.contrib.auth` is in BOTH app lists, so `auth_user` resolves to the
#:     BOUTIQUE's table.
#:
#: Put together: send `X-Tenant-ID: <your own boutique>` to /admin/login/,
#: authenticate as your own boutique's superuser -- an account seed_data.py
#: creates and any boutique can hold -- and Django's admin then administers the
#: PLATFORM's registry. Confirmed against this build: such an account read the
#: full boutique list, read the platform audit log, and SUSPENDED a different
#: boutique. IsPlatformAdmin never ran, because /admin/ is not a DRF view.
#:
#: Pinning to public means the admin authenticates against public.auth_user, so
#: only a real platform administrator can sign in.
#:
#: KNOWN CONSEQUENCE, accepted deliberately: the ModelAdmins in crm_api/admin.py
#: cover TENANT models, whose tables do not exist in public, so those pages stop
#: working. They were only ever reachable by binding a tenant to /admin/ -- which
#: is the escalation above -- and were already broken for the platform
#: administrator this console is built for. A boutique's own data is edited in
#: the boutique's workspace, where its business rules run, and read in the
#: console's data browser.
PUBLIC_ONLY_PREFIXES = (SUPERADMIN_PREFIX, '/admin/')


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


#: The columns that decide whether a request is ALLOWED, as opposed to the ones
#: that decide what it is called. These are never served from the cache above.
_CONTROL_COLUMNS = ('is_active', 'enabled_modules')


class TenantGone(Exception):
    """The registry row for a tenant vanished between resolution and the check."""


def _control_state(tenant_model, tenant):
    """`is_active` and `enabled_modules`, read from the database every time.

    The cache above exists because resolving a tenant is per-request overhead on
    a value that essentially never changes. Suspension is not that value.

    A suspension is a security decision an administrator takes and is told has
    taken effect. Serving it from a per-worker cache made that false: gunicorn
    runs two workers, the console clears only its own, and the other kept
    answering 200 for a boutique the database said was switched off -- measured,
    not reasoned about. Nothing about "we already know this boutique's name"
    justifies also assuming it is still allowed in.

    So identity stays cached and authority does not. The cost is one indexed
    single-row SELECT of two columns per tenant request, which is what the
    invariant is worth: once a suspension is committed, the next request is
    refused, in every worker, with no TTL in between.

    Raises TenantGone when the row has been deleted. Fail closed: a tenant that
    is no longer in the registry must not keep being served from a cached copy
    of the row that used to be there.
    """
    row = (tenant_model.objects.filter(pk=tenant.pk)
           .values(*_CONTROL_COLUMNS).first())
    if row is None:
        raise TenantGone(tenant.schema_name)
    return row


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
    indexed single-row SELECT per call -- which is exactly what _control_state
    above now does for suspension.

    Left cached here, and the difference is the point: suspension is an
    AUTHORIZATION decision about one boutique and had to become authoritative,
    while maintenance mode is a platform-wide AVAILABILITY switch that is read
    on every request including the ones that resolve no tenant at all. Paying a
    query per request for a row that is false ~100% of the time buys nothing
    security-relevant. The residual defect is availability only, it is bounded
    at _TENANT_CACHE_TTL, and it is documented in the production-readiness
    notes rather than fixed here.
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


def _activate_tenant_timezone(tenant):
    """Render this request's datetimes in the boutique's own timezone.

    A boutique in Chennai and one in Dubai read different clocks off the same
    stored instant, so the zone is a property of the tenant rather than of the
    deployment. settings.TIME_ZONE stays UTC and the database is untouched.
    """
    from core.formatting import tenant_timezone
    timezone.activate(tenant_timezone(tenant))


class TenantHeaderMiddleware(TenantMainMiddleware):
    #: The answer a boutique with no schema gets, wherever it is discovered.
    #: 503 rather than 403 or 400: the caller and their credentials are fine and
    #: the boutique is real. What is missing is server-side state an operator has
    #: to restore, and retrying afterwards is the correct thing for a client to do.
    UNAVAILABLE = {"error": "This boutique is temporarily unavailable. "
                            "Please contact support."}

    def process_exception(self, request, exception):
        """Turn a refused schema switch into a 503 instead of a 500.

        `process_request` below catches this for requests that name their tenant
        in a header, but several views resolve their own tenant and only reach
        the guard once they try to enter it -- login, password reset and the
        public order-tracking page among them. Before the guard existed those
        requests silently read the public schema; with it they raise, and without
        this they would raise all the way out as an unhandled 500, taking a
        traceback to the caller and filing an ErrorEvent for what is a known
        operational state rather than a bug in the code.

        Handled here rather than in each view for the same reason the guard
        itself is in one place: the next view that resolves its own tenant
        inherits this without anyone remembering.
        """
        from superadmin.schemas import MissingSchema
        if isinstance(exception, MissingSchema):
            logger.error('%s', exception)
            connection.set_schema_to_public()
            return JsonResponse(self.UNAVAILABLE, status=503)
        return None

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
        # And /admin/ is pinned for a fourth reason that is a live privilege
        # escalation rather than a design preference -- see PUBLIC_ONLY_PREFIXES.
        #
        # Pinned before anything is read, so no later branch can undo it.
        if request.path.startswith(PUBLIC_ONLY_PREFIXES):
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
                    # A boutique whose schema does not exist is SKIPPED, not
                    # searched. Postgres ignores a missing entry in search_path,
                    # and `authtoken` is a SHARED_APP -- so entering a ghost
                    # schema aims this lookup at public, where every token on
                    # the platform lives, and the FIRST ghost in the registry
                    # therefore matches any token at all.
                    #
                    # Measured, not reasoned about: with one ghost row present,
                    # GET /api/auth/me/ carrying the platform console's own
                    # token answered 200 and reported tenant_id = the ghost.
                    # The console's administrator was admitted as a boutique
                    # user of a boutique that does not exist, and every query
                    # afterwards ran against public.
                    if not _schema_exists(t.schema_name):
                        continue
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

        # Everything from here to set_tenant() is the authorization gate, and it
        # runs against the DATABASE rather than against the cached tenant object
        # resolved above. See _control_state.
        control = {'is_active': True, 'enabled_modules': {}}
        if tenant is not None and tenant.schema_name != public_schema_name:
            try:
                control = _control_state(tenant_model, tenant)
            except TenantGone:
                # The registry row was deleted while this worker still had it
                # cached. Same answer as a tenant id that never existed.
                _tenant_cache.pop(tenant.schema_name, None)
                return JsonResponse(
                    {"error": f"Unknown tenant '{tenant.schema_name}'."}, status=400)

            # A registry row whose Postgres schema is absent must never become
            # the connection's schema. `SET search_path = 'ghost', public`
            # succeeds -- Postgres skips the missing entry -- and every query
            # then resolves against public, where auth_user and authtoken_token
            # really do exist because auth is a SHARED_APP. Nothing raises.
            #
            # superadmin/schemas.py closed this for the console. This closes it
            # for the product, which is where the request path actually is:
            # this middleware is the single place a boutique becomes the
            # connection's schema, so guarding here covers every view, every
            # read and every write at once rather than one caller at a time.
            #
            # 503, not 403 or 400: the caller and their token are fine and the
            # boutique is real. What is missing is server-side state an operator
            # has to restore, and a retry after they have is the correct thing
            # for a client to do.
            if not _schema_exists(tenant.schema_name):
                logger.error(
                    'Tenant %r has a registry row but no database schema. '
                    'Refusing the request rather than resolving it against the '
                    'public schema.', tenant.schema_name)
                return JsonResponse(self.UNAVAILABLE, status=503)

        # A suspended boutique is refused here, after every resolution path
        # above has had its turn, because this is the single point where a
        # tenant becomes the connection's schema. Guarding each path separately
        # would leave the next one added unguarded.
        #
        # 403 rather than 400: the tenant exists and the caller's token is
        # genuine, and the frontend already treats 400 from here as "bad tenant
        # id, retry" while 403 surfaces the message.
        if not control['is_active']:
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
        # Read from `control`, not from the cached tenant: a module switch is an
        # access decision the console reports as applied, and it rode the same
        # stale copy the suspension check did.
        if tenant is not None:
            module = module_for_path(request.path)
            if module is not None and not is_enabled(control['enabled_modules'], module):
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

        if tenant and tenant.schema_name != public_schema_name:
            tenant.domain_url = request.get_host()
            request.tenant = tenant
            connection.set_tenant(request.tenant)
            # Presentation only. Storage stays UTC -- activate() changes how a
            # datetime is RENDERED for the rest of this request, never how it is
            # written. Bound here because this is the one place every request
            # already resolves its boutique, so no view has to remember to.
            _activate_tenant_timezone(tenant)
            self.setup_url_routing(request)
        else:
            connection.set_schema_to_public()
            timezone.deactivate()
            if request.path.startswith('/api/') and not request.path.startswith(PUBLIC_ONLY_PREFIXES) and not request.path.startswith('/api/auth/'):
                return JsonResponse(
                    {"error": "Boutique tenant context required for this endpoint. If you are a Superadmin, please use the Superadmin Console at /superadmin.html."},
                    status=400,
                )


