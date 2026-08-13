import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'boutique_crm.settings')
django.setup()

from django.contrib.auth.models import User
from crm_api.models import Tailor, BoutiqueFabric, BoutiqueDesign
from tenants.models import BoutiqueTenant, Domain
from core.utils import refuse_unless_local_database
from django_tenants.utils import schema_context

def seed():
    refuse_unless_local_database()
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
        # No literal password. This used to create the platform administrator
        # -- the account that lists, browses and suspends every boutique -- as
        # admin/admin123, and that row is in the committed SQL dump. Worse, it
        # took the name create_superuser.py also uses, and that script used to
        # skip when the account existed: so the deploy-time rotation reported
        # success on every redeploy while leaving this password in place.
        #
        # A local seed does not need a superuser at all; create_superuser.py is
        # what makes one, from the environment, and now rotates it every deploy.
        if not User.objects.filter(username='admin').exists():
            print("No superuser in public schema. Create one with:")
            print("  DJANGO_SUPERUSER_PASSWORD=... python create_superuser.py")
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
                password=os.environ.get('SEED_OWNER_PASSWORD', 'seed-only-not-for-real-use'),
                first_name='Aditi',
                last_name='Mehta'
            )
            print(f"Owner account created in tenant: {owner_email} "
                  f"(password from SEED_OWNER_PASSWORD)")
        else:
            print(f"Owner account in tenant already exists")

        from crm_api.utils import seed_tenant_defaults
        seed_tenant_defaults()
        print("Catalog and tailors seeded inside tenant schema")

    print("Seeding completed successfully!")

if __name__ == '__main__':
    seed()
