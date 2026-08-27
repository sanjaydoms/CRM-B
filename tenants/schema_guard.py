
from django_tenants.utils import get_public_schema_name


def enforce_tenant_schema(connection, tenant):
    schema_name = getattr(tenant, 'schema_name', None)
    public = get_public_schema_name()

    if not schema_name or schema_name == public:
        return

    from superadmin.schemas import MissingSchema, schema_exists

    if schema_exists(schema_name):
        return

    connection.set_schema_to_public()
    raise MissingSchema(
        f"Boutique '{schema_name}' has a registry row but no database schema. "
        f"Refusing to point the connection at it, because Postgres would "
        f"silently resolve every query against the public schema instead."
    )
