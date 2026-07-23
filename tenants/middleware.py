from django.db import connection
from django_tenants.middleware.main import TenantMainMiddleware
from django_tenants.utils import get_tenant_model, get_public_schema_name, get_tenant_domain_model, schema_context

class TenantHeaderMiddleware(TenantMainMiddleware):
    def process_request(self, request):
        # 1. First, check request headers for X-Tenant-ID
        tenant_schema = request.headers.get("X-Tenant-ID")
        
        tenant_model = get_tenant_model()
        public_schema_name = get_public_schema_name()
        
        tenant = None
        if tenant_schema and tenant_schema != 'public':
            try:
                tenant = tenant_model.objects.get(schema_name=tenant_schema)
            except tenant_model.DoesNotExist:
                pass
        
        # 2. If not resolved via header, fallback to Authorization Token context search
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
                try:
                    tenant = tenant_model.objects.get(schema_name=public_schema_name)
                except tenant_model.DoesNotExist:
                    tenant = None
        
        if tenant:
            tenant.domain_url = request.get_host()
            request.tenant = tenant
            connection.set_tenant(request.tenant)
            self.setup_url_routing(request)
        else:
            connection.set_schema_to_public()
