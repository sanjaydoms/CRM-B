import time

from django.db import connection
from django.http import JsonResponse
from django_tenants.middleware.main import TenantMainMiddleware
from django_tenants.utils import get_tenant_model, get_public_schema_name, get_tenant_domain_model, schema_context

# Resolving the tenant is the first thing every request does, and it used to cost
# a database round trip before any application query could start -- on a hosted
# database that is tens of milliseconds added to literally every call. Tenants
# are created at sign-up and then essentially never change, so they are cached in
# process for a short window. The TTL is what keeps a newly created or renamed
# tenant from being invisible to already-running workers; it does not need to be
# long, because the saving is per-request rather than per-window.
_TENANT_CACHE_TTL = 300
_tenant_cache = {}


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


class TenantHeaderMiddleware(TenantMainMiddleware):
    def process_request(self, request):
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

        if tenant:
            tenant.domain_url = request.get_host()
            request.tenant = tenant
            connection.set_tenant(request.tenant)
            self.setup_url_routing(request)
        else:
            connection.set_schema_to_public()
