
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from tenants.models import BoutiqueTenant
from tenants.provision import (
    BASE_NAME, BASE_OWNER_EMAIL, install_clone_function,
)


class Command(BaseCommand):
    help = "Create or refresh the template schema signup clones (settings.TENANT_BASE_SCHEMA)."

    def handle(self, *args, **options):
        from django_tenants.utils import schema_exists

        schema = settings.TENANT_BASE_SCHEMA
        row = BoutiqueTenant.objects.filter(schema_name=schema).first()

        with transaction.atomic():
            if row is None:
                row = BoutiqueTenant(
                    schema_name=schema,
                    owner_email=BASE_OWNER_EMAIL,
                    name=BASE_NAME,
                    is_active=False,  # never signs in, never serves requests
                )
                if schema_exists(schema):
                    self.stdout.write(f"Adopting existing schema '{schema}'...")
                    row.auto_create_schema = False
                else:
                    self.stdout.write(
                        f"Creating base schema '{schema}' (full migrate -- slow, once)...")
                row.save()
            elif not schema_exists(schema):
                self.stdout.write(f"Schema '{schema}' missing; rebuilding...")
                row.create_schema(check_if_exists=True)

            if row.is_active:
                row.is_active = False
                row.save(update_fields=['is_active'])

            call_command('migrate_schemas', tenant=True, schema_name=schema,
                         interactive=False, verbosity=0)

            install_clone_function()

        from django.db import connection
        connection.set_schema_to_public()

        self.stdout.write(self.style.SUCCESS(
            f"Base '{schema}' ready; new signups will clone it in seconds."
        ))
