import sys, os
sys.path.insert(0, os.path.abspath('.'))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'boutique_crm.settings')
django.setup()

from tenants.models import BoutiqueTenant
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from django_tenants.utils import schema_context

with schema_context('public'):
    tenants = list(BoutiqueTenant.objects.all())
    print("ALL TENANTS IN PUBLIC REGISTRY:")
    for t in tenants:
        print(f" - schema_name: '{t.schema_name}', owner_email: '{t.owner_email}', is_active: {t.is_active}")

print("\nUSERS & TOKENS PER SCHEMA:")
for t in tenants:
    with schema_context(t.schema_name):
        users = list(User.objects.all())
        tokens = list(Token.objects.all())
        print(f"\nSchema '{t.schema_name}': {len(users)} users, {len(tokens)} tokens")
        for u in users:
            tok = Token.objects.filter(user=u).first()
            tok_str = tok.key if tok else "NO TOKEN"
            print(f"   User id={u.id}, username='{u.username}', email='{u.email}', is_superuser={u.is_superuser}, token={tok_str}")
