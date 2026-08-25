"""The one place a schema becomes the connection's schema, guarded.

WHY THIS EXISTS
---------------
django-tenants selects a tenant with ``SET search_path = '<schema>', public``.
Postgres accepts a search_path naming a schema that is not there -- it silently
skips it. Because ``django.contrib.auth`` and ``rest_framework.authtoken`` are in
SHARED_APPS *and* TENANT_APPS, ``auth_user`` and ``authtoken_token`` really do
exist in ``public``. So every query issued "inside" a missing tenant resolves
against the platform's own rows, returns them, and raises nothing.

``superadmin/schemas.py`` closed this for the console, and ``TenantHeaderMiddleware``
closed it for the ordinary request path. Neither covers code that resolves its
own tenant, and three such paths were still open -- all reachable without
authenticating:

  * ``crm_api.auth_views.find_tenants_for_account`` walks every registry row
    looking for an account, so a ghost row made the scan read ``public``. Used by
    login *and* by password reset.
  * ``PasswordResetRequestView`` then minted a genuine reset token for whatever
    user that scan found. Measured on this build: requesting a reset for the
    PLATFORM ADMINISTRATOR's address produced a valid token naming the ghost
    schema, and ``PasswordResetConfirmView`` -- which takes its schema from
    request-body text -- accepted it and **overwrote the platform
    administrator's password**.
  * ``crm_api.tracking_views.order_tracking`` is public and unauthenticated.

Patching those three call sites would have left the fourth one, and every one
written afterwards. ``connection.set_tenant()`` is the single function they all
end in: ``schema_context`` calls ``set_schema`` which calls ``set_tenant``,
``tenant_context`` calls ``set_tenant``, and ``TenantMixin.activate`` calls
``set_tenant``. django-tenants publishes ``EXTRA_SET_TENANT_METHOD_PATH`` as the
supported hook into exactly that function, so this is the shared boundary rather
than a fourth patch, and it covers code that does not exist yet.

WHAT IT DOES NOT BREAK
----------------------
* ``public`` is always allowed, so ``set_schema_to_public()`` -- which runs on
  every request that resolves no tenant, and in every ``__exit__`` -- is free.
* Schema CREATION is safe: ``TenantMixin.create_schema`` issues ``CREATE SCHEMA``
  *before* ``migrate_schemas`` switches into it, so by the time anything reaches
  here the schema is real.
* The check is one ``pg_namespace`` lookup per schema per process; positive
  results are cached in ``superadmin.schemas._present``, so steady state is a set
  membership test.
"""

from django_tenants.utils import get_public_schema_name


def enforce_tenant_schema(connection, tenant):
    """django-tenants' EXTRA_SET_TENANT_METHOD hook. Refuse absent schemas.

    Raises ``superadmin.schemas.MissingSchema`` rather than letting the switch
    proceed. Raising is the whole point: the failure this prevents is silent, so
    the only safe outcome is a loud one.

    The connection is put back on ``public`` before raising. Without that it
    would be left pointing at a schema Postgres will quietly resolve to
    ``public`` anyway, and any caller that swallowed the exception would carry
    on in exactly the state this exists to prevent.
    """
    schema_name = getattr(tenant, 'schema_name', None)
    public = get_public_schema_name()

    if not schema_name or schema_name == public:
        return

    # Imported here, not at module scope: this module is resolved by
    # django-tenants' database backend while Django is still starting, long
    # before the app registry is ready.
    from superadmin.schemas import MissingSchema, schema_exists

    if schema_exists(schema_name):
        return

    connection.set_schema_to_public()
    raise MissingSchema(
        f"Boutique '{schema_name}' has a registry row but no database schema. "
        f"Refusing to point the connection at it, because Postgres would "
        f"silently resolve every query against the public schema instead."
    )
