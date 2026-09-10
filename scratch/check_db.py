import sys, os
sys.path.insert(0, os.path.abspath('.'))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'boutique_crm.settings')
django.setup()

from django.db import connection

with connection.cursor() as cursor:
    cursor.execute("SELECT schema_name FROM tenants_boutiquetenant;")
    tenants = [row[0] for row in cursor.fetchall()]
    print("Found tenant schemas in DB:", tenants)

    for tenant in tenants:
        cursor.execute(f'SET search_path TO "{tenant}";')
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = %s AND table_name LIKE 'crm_api%%';", [tenant])
        tables = [r[0] for r in cursor.fetchall()]
        print(f"Tenant '{tenant}' crm_api tables ({len(tables)}):", sorted(tables))
        has_orderstage = 'crm_api_orderstage' in tables
        print(f"  -> has crm_api_orderstage: {has_orderstage}")
