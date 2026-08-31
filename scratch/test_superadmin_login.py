import sys, os
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.path.abspath('.'))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'boutique_crm.settings')
django.setup()

from rest_framework.test import APIRequestFactory
from superadmin.views import PlatformLoginView
from django.contrib.auth.models import User
from django_tenants.utils import schema_context

factory = APIRequestFactory()
platform_login_view = PlatformLoginView.as_view()

with schema_context('public'):
    u = User.objects.filter(username='Super Admin').first()
    if u:
        u.set_password('MSK1122@crm')
        u.save()

req = factory.post('/api/superadmin/auth/login/', {'username': 'Super Admin', 'password': 'MSK1122@crm'}, format='json')
resp = platform_login_view(req)
print("PlatformLoginView status:", resp.status_code, flush=True)
print("PlatformLoginView response data:", resp.data, flush=True)
