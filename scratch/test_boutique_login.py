import sys, os
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.path.abspath('.'))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'boutique_crm.settings')
django.setup()

from rest_framework.test import APIRequestFactory
from crm_api.auth_views import LoginView
from django.contrib.auth.models import User
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token
from tenants.middleware import TenantHeaderMiddleware

factory = APIRequestFactory()
login_view = LoginView.as_view()
middleware = TenantHeaderMiddleware(lambda req: None)

# Reset password for sanjay.garlapenta@domsglobal.co
with schema_context('sanjay_garlapenta_domsglobal_co'):
    u = User.objects.filter(email='sanjay.garlapenta@domsglobal.co').first()
    if u:
        u.set_password('TailorSecure2026!')
        u.save()
        print("Reset sanjay password")

req = factory.post('/api/auth/login/', {'username': 'sanjay.garlapenta@domsglobal.co', 'password': 'TailorSecure2026!'}, format='json')
resp = login_view(req)
print("Login status:", resp.status_code)
print("Login response data:", resp.data)

if resp.status_code == 200:
    token = resp.data['token']
    tenant_id = resp.data['tenant_id']
    
    # 1. Test GET /api/orders/ WITH X-Tenant-ID
    req_orders_valid = factory.get('/api/orders/', HTTP_AUTHORIZATION=f'Token {token}', HTTP_X_TENANT_ID=tenant_id)
    mw1 = middleware.process_request(req_orders_valid)
    print("GET /api/orders/ WITH X-Tenant-ID -> MW:", mw1, "tenant:", getattr(req_orders_valid, 'tenant', 'PUBLIC'))
    
    # 2. Test GET /api/orders/ WITHOUT X-Tenant-ID
    req_orders_no_header = factory.get('/api/orders/', HTTP_AUTHORIZATION=f'Token {token}')
    mw2 = middleware.process_request(req_orders_no_header)
    print("GET /api/orders/ WITHOUT X-Tenant-ID -> MW:", mw2, "tenant:", getattr(req_orders_no_header, 'tenant', 'PUBLIC'))
