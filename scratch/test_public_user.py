import sys, os
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.path.abspath('.'))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'boutique_crm.settings')
django.setup()

from rest_framework.test import APIRequestFactory
from tenants.middleware import TenantHeaderMiddleware
from django.contrib.auth.models import User
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token

factory = APIRequestFactory()
middleware = TenantHeaderMiddleware(lambda req: None)

with schema_context('public'):
    u = User.objects.filter(username='Super Admin').first()
    tok, _ = Token.objects.get_or_create(user=u)
    token = tok.key

print("Testing request with Superadmin token (public schema)...")
headers = {'HTTP_AUTHORIZATION': f'Token {token}'}

for endpoint in ['/api/dashboard/', '/api/customers/', '/api/orders/', '/api/tailors/']:
    req = factory.get(endpoint, **headers)
    mw_res = middleware.process_request(req)
    if mw_res:
        print(f"Endpoint {endpoint} -> Middleware returned HTTP {mw_res.status_code}: {mw_res.content.decode()}")
    else:
        print(f"Endpoint {endpoint} -> Allowed through to view on schema: {getattr(req, 'tenant', 'PUBLIC')}")
