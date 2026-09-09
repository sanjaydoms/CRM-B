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
    from superadmin.schemas import schema_exists
    return schema_exists(schema_name)

_TENANT_CACHE_TTL = 300
_tenant_cache = {}

SUPERADMIN_PREFIX = '/api/superadmin/'

PUBLIC_ONLY_PREFIXES = (SUPERADMIN_PREFIX, '/admin/')

#: Endpoints under /api/ that are legitimately reachable without a boutique.
#: Everything else there is refused with "tenant context required", because
#: serving it from the public schema is how a request meant for one boutique
#: reads the registry instead.
#:
#: `/api/auth/` is the front door -- you cannot name your boutique before you
#: have signed in to it. `/api/client-errors/` is the browser saying it crashed,
#: which is most likely to happen on the login screen, before any tenant is
#: known. Both are additions to this list, not exceptions to the rule.
TENANT_OPTIONAL_PREFIXES = ('/api/auth/', '/api/client-errors/')


def _get_tenant_by_schema(tenant_model, schema_name):
    hit = _tenant_cache.get(schema_name)
    now = time.monotonic()
    if hit is not None and hit[1] > now:
        return hit[0]
    try:
        tenant = tenant_model.objects.get(schema_name=schema_name)
    except tenant_model.DoesNotExist:
        tenant = None
    _tenant_cache[schema_name] = (tenant, now + _TENANT_CACHE_TTL)
    return tenant


def clear_tenant_cache():
    _tenant_cache.clear()


_CONTROL_COLUMNS = ('is_active', 'enabled_modules')


class TenantGone(Exception):
    pass



def _control_state(tenant_model, tenant):
    row = (tenant_model.objects.filter(pk=tenant.pk)
           .values(*_CONTROL_COLUMNS).first())
    if row is None:
        raise TenantGone(tenant.schema_name)
    return row


_platform_cache = {}


def clear_platform_cache():
    _platform_cache.clear()


def _maintenance_mode():
    hit = _platform_cache.get('maintenance_mode')
    now = time.monotonic()
    if hit is not None and hit[1] > now:
        return hit[0]

    value = None
    try:
        from superadmin.models import PlatformSetting
        with schema_context(get_public_schema_name()):
            row = PlatformSetting.objects.filter(key='maintenance_mode').first()
        if row and isinstance(row.value, dict) and row.value.get('enabled'):
            value = row.value
    except Exception:
        value = None

    _platform_cache['maintenance_mode'] = (value, now + _TENANT_CACHE_TTL)
    return value


def _activate_tenant_timezone(tenant):
    from core.formatting import tenant_timezone
    timezone.activate(tenant_timezone(tenant))


class TenantHeaderMiddleware(TenantMainMiddleware):
    UNAVAILABLE = {"error": "This boutique is temporarily unavailable. "
                            "Please contact support."}

    def _refuse(self, request, payload, status, *, reason, boutique=''):
        """
        Refuse a request and leave a trace of it.

        Every refusal below is a platform control doing its job -- suspension, a
        switched-off module, maintenance, a boutique whose schema is gone. Until
        this existed none of them were recorded anywhere, so the Super Admin
        console could switch a module off and have no way to see it bite, and a
        boutique locked out by its own suspension looked identical to a boutique
        that had simply stopped using the product.

        Routed through one helper rather than eight call sites so the response
        and the record cannot drift apart: you cannot add a refusal here and
        forget to file it.
        """
        from core.exceptions import record_refusal
        record_refusal(request, reason=reason,
                       message=payload.get('error', ''),
                       status_code=status, boutique=boutique)
        return JsonResponse(payload, status=status)

    def process_exception(self, request, exception):
        from superadmin.schemas import MissingSchema
        if isinstance(exception, MissingSchema):
            logger.error('%s', exception)
            connection.set_schema_to_public()
            return self._refuse(request, self.UNAVAILABLE, 503,
                                reason='MissingSchema')
        return None

    def process_request(self, request):
        if request.path.startswith(PUBLIC_ONLY_PREFIXES):
            connection.set_schema_to_public()
            return None

        maintenance = _maintenance_mode()
        if maintenance and not any(request.path.startswith(p) for p in ALWAYS_ON):
            return self._refuse(
                request,
                {"error": maintenance.get('message')
                          or "The platform is down for maintenance. Please try again shortly.",
                 "maintenance": True},
                503, reason='MaintenanceMode')

        tenant_schema = request.headers.get("X-Tenant-ID")

        tenant_model = get_tenant_model()
        public_schema_name = get_public_schema_name()

        tenant = None
        if tenant_schema and tenant_schema != 'public':
            tenant = _get_tenant_by_schema(tenant_model, tenant_schema)
            if tenant is None:
                return self._refuse(
                    request, {"error": f"Unknown tenant '{tenant_schema}'."}, 400,
                    reason='UnknownTenant')

        if not tenant:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Token "):
                token_key = auth_header.split(" ")[1]
                for t in tenant_model.objects.exclude(schema_name='public'):
                    if not _schema_exists(t.schema_name):
                        continue
                    with schema_context(t.schema_name):
                        from rest_framework.authtoken.models import Token
                        if Token.objects.filter(key=token_key).exists():
                            tenant = t
                            break

        if not tenant:
            hostname = self.hostname_from_request(request)
            domain_model = get_tenant_domain_model()
            try:
                domain = domain_model.objects.select_related('tenant').get(domain=hostname)
                tenant = domain.tenant
            except domain_model.DoesNotExist:
                tenant = _get_tenant_by_schema(tenant_model, public_schema_name)

        control = {'is_active': True, 'enabled_modules': {}}
        if tenant is not None and tenant.schema_name != public_schema_name:
            try:
                control = _control_state(tenant_model, tenant)
            except TenantGone:
                _tenant_cache.pop(tenant.schema_name, None)
                return self._refuse(
                    request, {"error": f"Unknown tenant '{tenant.schema_name}'."}, 400,
                    reason='TenantGone', boutique=tenant.schema_name)

            if not _schema_exists(tenant.schema_name):
                logger.error(
                    'Tenant %r has a registry row but no database schema. '
                    'Refusing the request rather than resolving it against the '
                    'public schema.', tenant.schema_name)
                return self._refuse(request, self.UNAVAILABLE, 503,
                                    reason='MissingSchema',
                                    boutique=tenant.schema_name)

        if not control['is_active']:
            return self._refuse(
                request,
                {"error": "This boutique's access has been suspended. "
                          "Please contact support."},
                403, reason='BoutiqueSuspended',
                boutique=getattr(tenant, 'schema_name', ''))

        if tenant is not None:
            module = module_for_path(request.path)
            if module is not None and not is_enabled(control['enabled_modules'], module):
                # The module goes in the reason, not just the message, so the
                # console shows one row per switched-off module rather than one
                # row for "a module was off" that keeps rewriting itself.
                return self._refuse(
                    request,
                    {"error": f"The {MODULES[module][0]} module is switched off for "
                              f"this boutique. Contact platform support to enable it.",
                     "module": module},
                    403, reason=f'ModuleDisabled:{module}',
                    boutique=getattr(tenant, 'schema_name', ''))

        if tenant and tenant.schema_name != public_schema_name:
            tenant.domain_url = request.get_host()
            request.tenant = tenant
            connection.set_tenant(request.tenant)
            _activate_tenant_timezone(tenant)
            self.setup_url_routing(request)
        else:
            connection.set_schema_to_public()
            timezone.deactivate()
            if (request.path.startswith('/api/')
                    and not request.path.startswith(PUBLIC_ONLY_PREFIXES)
                    and not request.path.startswith(TENANT_OPTIONAL_PREFIXES)):
                return self._refuse(
                    request,
                    {"error": "Boutique tenant context required for this endpoint. If you are a Superadmin, please use the Superadmin Console at /superadmin.html."},
                    400, reason='TenantContextRequired')


