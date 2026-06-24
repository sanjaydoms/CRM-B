import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'boutique_crm.settings')
django.setup()

from django.contrib.auth.models import User
from crm_api.models import Tailor, BoutiqueFabric, BoutiqueDesign
from tenants.models import BoutiqueTenant, Domain
from django_tenants.utils import schema_context

def seed():
    # 1. Create Public Tenant Registry
    if not BoutiqueTenant.objects.filter(schema_name='public').exists():
        public_tenant = BoutiqueTenant.objects.create(
            schema_name='public',
            owner_email='admin@boutique.com',
            name='Public Registry'
        )
        Domain.objects.create(
            domain='localhost',
            tenant=public_tenant,
            is_primary=True
        )
        print("Public tenant registry created")
    else:
        print("Public tenant registry already exists")

    # 2. Create Superuser in Public Schema
    with schema_context('public'):
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@boutique.com', 'admin123')
            print("Superuser created in public schema: admin / admin123")
        else:
            print("Superuser in public schema already exists")

    # 3. Create Default Test Boutique Owner Tenant
    owner_email = 'owner@tryon2buy.com'
    owner_schema = 'owner_tryon2buy_com'
    
    if not BoutiqueTenant.objects.filter(schema_name=owner_schema).exists():
        owner_tenant = BoutiqueTenant.objects.create(
            schema_name=owner_schema,
            owner_email=owner_email,
            name="Aditi's Boutique"
        )
        Domain.objects.create(
            domain='owner.localhost',
            tenant=owner_tenant,
            is_primary=True
        )
        print(f"Default tenant schema '{owner_schema}' created")
    else:
        print(f"Default tenant schema '{owner_schema}' already exists")

    # 4. Seed User & Catalog inside the Owner Tenant Schema
    with schema_context(owner_schema):
        # Create Owner User account
        if not User.objects.filter(username=owner_email).exists():
            User.objects.create_user(
                username=owner_email,
                email=owner_email,
                password='password123',
                first_name='Aditi',
                last_name='Mehta'
            )
            print(f"Owner account created in tenant: {owner_email} / password123")
        else:
            print(f"Owner account in tenant already exists")

        from crm_api.utils import seed_tenant_defaults
        seed_tenant_defaults()
        print("Catalog and tailors seeded inside tenant schema")

    print("Seeding completed successfully!")

if __name__ == '__main__':
    seed()
