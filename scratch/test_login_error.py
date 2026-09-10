import sys, os
sys.path.insert(0, os.path.abspath('.'))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'boutique_crm.settings')
django.setup()

from rest_framework.test import APIRequestFactory
from crm_api.views import OrderViewSet
from django.contrib.auth.models import User
from tenants.models import BoutiqueTenant
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token
from tenants.middleware import TenantHeaderMiddleware

factory = APIRequestFactory()
middleware = TenantHeaderMiddleware(lambda req: None)

print("=== Scenario 1: Superadmin user in public schema ===")
with schema_context('public'):
    admin_user = User.objects.filter(is_superuser=True).first()
    if admin_user:
        token, _ = Token.objects.get_or_create(user=admin_user)
        print("Admin user found:", admin_user.username, "Token:", token.key[:8]+"...")
        
        request = factory.get('/api/orders/', HTTP_AUTHORIZATION=f'Token {token.key}')
        res = middleware.process_request(request)
        if res:
            print("Middleware intercepted request and returned status:", res.status_code)
            print("Response body:", res.content.decode())
        else:
            print("Middleware allowed request to proceed to view")

print("\n=== Scenario 2: Boutique tenant user ===")
with schema_context('public'):
    tenants = list(BoutiqueTenant.objects.exclude(schema_name='public'))
    if tenants:
        t = tenants[0]
        print("Testing with tenant:", t.schema_name)
        with schema_context(t.schema_name):
            b_user = User.objects.first()
            if b_user:
                b_token, _ = Token.objects.get_or_create(user=b_user)
                
                # Request WITH X-Tenant-ID header
                request_with_header = factory.get('/api/orders/', HTTP_AUTHORIZATION=f'Token {b_token.key}', HTTP_X_TENANT_ID=t.schema_name)
                res_mw1 = middleware.process_request(request_with_header)
                print("With X-Tenant-ID middleware response:", res_mw1)
                
                # Request WITHOUT X-Tenant-ID header
                request_no_header = factory.get('/api/orders/', HTTP_AUTHORIZATION=f'Token {b_token.key}')
                res_mw2 = middleware.process_request(request_no_header)
                print("Without X-Tenant-ID middleware response:", res_mw2)
