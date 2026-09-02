import sys, os
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.path.abspath('.'))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'boutique_crm.settings')
django.setup()

from rest_framework.test import APIRequestFactory
from crm_api.auth_views import LoginView
from crm_api.views import OrderViewSet, DashboardView, TailorViewSet
from tenants.middleware import TenantHeaderMiddleware

factory = APIRequestFactory()
middleware = TenantHeaderMiddleware(lambda req: None)

test_accounts = [
    ("admin", "MSK1122@crm"),
    ("Super Admin", "MSK1122@crm"),
    ("owner@tryon2buy.com", "TailorSecure2026!"),
    ("sanjay.garlapenta@domsglobal.co", "TailorSecure2026!"),
    ("barsha@gmail.com", "TailorSecure2026!"),
    ("shankar@gmail.com", "TailorSecure2026!"),
]

login_view = LoginView.as_view()

for username, password in test_accounts:
    print(f"\n================ Testing login for: '{username}' ================", flush=True)
    req = factory.post('/api/auth/login/', {'username': username, 'password': password}, format='json')
    resp = login_view(req)
    print("Login status:", resp.status_code, flush=True)
    if resp.status_code == 200:
        data = resp.data
        token = data.get('token')
        tenant_id = data.get('tenant_id')
        user_info = data.get('user')
        print(f" -> Token: '{token}', tenant_id: '{tenant_id}', role: '{user_info.get('role')}'", flush=True)
        
        # Test subsequent GET requests as frontend would send them (with X-Tenant-ID)
        headers_with_tenant = {'HTTP_AUTHORIZATION': f'Token {token}', 'HTTP_X_TENANT_ID': tenant_id}
        
        req_orders = factory.get('/api/orders/', **headers_with_tenant)
        mw_err1 = middleware.process_request(req_orders)
        if mw_err1:
            print(" -> /api/orders/ Middleware Error:", mw_err1.status_code, mw_err1.content.decode(), flush=True)
        else:
            v_orders = OrderViewSet.as_view({'get': 'list'})
            try:
                r_orders = v_orders(req_orders)
                print(" -> /api/orders/ Status:", r_orders.status_code, flush=True)
            except Exception as e:
                print(" -> /api/orders/ EXCEPTION:", type(e).__name__, e, flush=True)

        req_dash = factory.get('/api/dashboard/', **headers_with_tenant)
        mw_err2 = middleware.process_request(req_dash)
        if mw_err2:
            print(" -> /api/dashboard/ Middleware Error:", mw_err2.status_code, mw_err2.content.decode(), flush=True)
        else:
            v_dash = DashboardView.as_view()
            try:
                r_dash = v_dash(req_dash)
                print(" -> /api/dashboard/ Status:", r_dash.status_code, flush=True)
            except Exception as e:
                print(" -> /api/dashboard/ EXCEPTION:", type(e).__name__, e, flush=True)
    else:
        print(" -> Login failed:", resp.data, flush=True)
