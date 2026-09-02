
from django.conf import settings
from django.db import connection

from tenants.models import BoutiqueTenant

BASE_OWNER_EMAIL = 'tenant-base@platform.invalid'
BASE_NAME = '(template schema - do not use)'


def base_is_ready():
    from django_tenants.utils import schema_exists
    return (schema_exists(settings.TENANT_BASE_SCHEMA)
            and BoutiqueTenant.objects.filter(
                schema_name=settings.TENANT_BASE_SCHEMA).exists())


def provision_tenant(**fields):
    tenant = BoutiqueTenant(**fields)
    if base_is_ready():
        tenant.auto_create_schema = False
        tenant.save()
        with connection.cursor() as cursor:
            cursor.execute(
                'LOCK TABLE "%s".django_migrations IN SHARE MODE'
                % settings.TENANT_BASE_SCHEMA)
            cursor.execute(
                'SELECT clone_schema(%s, %s, %s)',
                [settings.TENANT_BASE_SCHEMA, tenant.schema_name, 'DATA'],
            )
    else:
        tenant.save()
    return tenant


def install_clone_function():
    from django_tenants.clone import CLONE_SCHEMA_FUNCTION
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_user')
        role = cursor.fetchone()[0]
        cursor.execute(CLONE_SCHEMA_FUNCTION.format(db_user=role))
