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

    def process_exception(self, request, exception):
        from superadmin.schemas import MissingSchema
        if isinstance(exception, MissingSchema):
            logger.error('%s', exception)
            connection.set_schema_to_public()
            return JsonResponse(self.UNAVAILABLE, status=503)
        return None

    def process_request(self, request):
        if request.path.startswith(PUBLIC_ONLY_PREFIXES):
            connection.set_schema_to_public()
            return None

        maintenance = _maintenance_mode()
        if maintenance and not any(request.path.startswith(p) for p in ALWAYS_ON):
            return JsonResponse(
                {"error": maintenance.get('message')
                          or "The platform is down for maintenance. Please try again shortly.",
                 "maintenance": True},
                status=503,
            )

        tenant_schema = request.headers.get("X-Tenant-ID")

        tenant_model = get_tenant_model()
        public_schema_name = get_public_schema_name()

        tenant = None
        if tenant_schema and tenant_schema != 'public':
            tenant = _get_tenant_by_schema(tenant_model, tenant_schema)
            if tenant is None:
                return JsonResponse(
                    {"error": f"Unknown tenant '{tenant_schema}'."}, status=400
                )

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
                return JsonResponse(
                    {"error": f"Unknown tenant '{tenant.schema_name}'."}, status=400)

            if not _schema_exists(tenant.schema_name):
                logger.error(
                    'Tenant %r has a registry row but no database schema. '
                    'Refusing the request rather than resolving it against the '
                    'public schema.', tenant.schema_name)
                return JsonResponse(self.UNAVAILABLE, status=503)

        if not control['is_active']:
            return JsonResponse(
                {"error": "This boutique's access has been suspended. "
                          "Please contact support."},
                status=403,
            )

        if tenant is not None:
            module = module_for_path(request.path)
            if module is not None and not is_enabled(control['enabled_modules'], module):
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
            _activate_tenant_timezone(tenant)
            self.setup_url_routing(request)
        else:
            connection.set_schema_to_public()
            timezone.deactivate()
