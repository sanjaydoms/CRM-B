
import logging

from django.db import connection, transaction
from django_tenants.utils import schema_context, tenant_context

logger = logging.getLogger(__name__)

_present = set()


def schema_exists(schema_name):
    if not schema_name:
        return False
    if schema_name in _present:
        return True
    from django_tenants.utils import schema_exists as _library_schema_exists
    found = _library_schema_exists(schema_name)
    if found:
        _present.add(schema_name)
    return found


def forget(schema_name):
    _present.discard(schema_name)


class MissingSchema(Exception):
    """Raised when a tenant schema does not exist in Postgres."""
    pass


def tenant_scope(tenant):
    if not schema_exists(tenant.schema_name):
        raise MissingSchema(
            f"Boutique '{tenant.schema_name}' has a registry row but no database "
            f"schema. Refusing to run against it, because Postgres would silently "
            f"resolve the query against the public schema instead."
        )
    return tenant_context(tenant)


def for_each_tenant(tenants, read):
    results, unreadable = [], []
    for tenant in tenants:
        try:
            with transaction.atomic():
                with tenant_scope(tenant):
                    results.append(read(tenant))
        except MissingSchema as exc:
            logger.warning('%s', exc)
            unreadable.append(tenant.schema_name)
        except Exception as exc:
            logger.warning('Boutique %s could not be read: %s', tenant.schema_name, exc)
            unreadable.append(tenant.schema_name)
    return results, unreadable


def public_scope():
    from django_tenants.utils import get_public_schema_name
    return schema_context(get_public_schema_name())
