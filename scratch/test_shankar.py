import sys, os
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.path.abspath('.'))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'boutique_crm.settings')
django.setup()

from rest_framework.test import APIRequestFactory
from crm_api.auth_views import LoginView
from crm_api.views import DashboardView, CustomerViewSet, OrderViewSet
from tenants.middleware import TenantHeaderMiddleware
from django.contrib.auth.models import User
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token

factory = APIRequestFactory()
middleware = TenantHeaderMiddleware(lambda req: None)

with schema_context('shankargmailcom_0f6864aa'):
    u = User.objects.filter(email='shankar@gmail.com').first()
    tok = Token.objects.get(user=u)
    token = tok.key

print("Testing WITHOUT X-Tenant-ID header...")
headers_no_tenant = {'HTTP_AUTHORIZATION': f'Token {token}'}

req_dash = factory.get('/api/dashboard/', **headers_no_tenant)
mw_res1 = middleware.process_request(req_dash)
print("Dashboard Middleware response:", mw_res1)
if mw_res1:
    print("Dashboard MW body:", mw_res1.content.decode())

req_cust = factory.get('/api/customers/', **headers_no_tenant)
mw_res2 = middleware.process_request(req_cust)
print("Customer Middleware response:", mw_res2)
if mw_res2:
    print("Customer MW body:", mw_res2.content.decode())

req_orders = factory.get('/api/orders/', **headers_no_tenant)
mw_res3 = middleware.process_request(req_orders)
print("Orders Middleware response:", mw_res3)
if mw_res3:
    print("Orders MW body:", mw_res3.content.decode())
