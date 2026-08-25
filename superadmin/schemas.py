"""Entering a boutique's schema safely.

The bug this exists to close is silent, cross-boundary, and was found by reading
django_tenants' backend rather than by anything failing:

    django_tenants selects a tenant with `SET search_path = 'the_schema', public`
    and does not check that `the_schema` exists.

Postgres accepts a search_path naming a schema that is not there. It simply
skips it. So every query issued "inside" a missing tenant resolves against the
next entry -- `public` -- and `auth`, `authtoken` and `contenttypes` are in
SHARED_APPS, which means `auth_user` and `authtoken_token` DO exist in public.

Nothing raises. The read returns rows. They are the platform's own rows.

Three real consequences, all confirmed against this database with a
BoutiqueTenant row pointing at a schema that was never created:

  * A cross-tenant READ. Searching a ghost boutique for users returned the
    platform console's own superuser, labelled as that boutique's staff.
  * A cross-tenant WRITE, which is the serious one. Deactivating a user in a
    ghost boutique deactivates the account of the same name in public -- and the
    console's own administrator lives in public. One click on a broken boutique
    disables the account that was clicking.
  * `try/except` cannot catch any of it, because there is no error. The code
    that "handles a broken schema" runs its happy path.

A tenant row without a schema is not hypothetical. `BoutiqueTenant.save()`
creates the schema, but a restored database dump, an interrupted signup, a
manually inserted row or a `delete(force_drop=False)` all leave one behind.

Everything that enters a tenant schema must go through `tenant_scope` here.
"""

import logging

from django.db import connection, transaction
from django_tenants.utils import schema_context, tenant_context

logger = logging.getLogger(__name__)

#: Schemas confirmed present, so the existence check is one query per schema per
#: process rather than one per operation. Only positive results are cached: a
#: schema that is missing now may be created a moment later by a signup, and
#: caching "absent" would make the new boutique invisible until the worker
#: restarted. A schema that exists is never un-created except by an explicit
#: force_drop, which calls forget() below.
_present = set()


def schema_exists(schema_name):
    """Whether `schema_name` is a real Postgres schema.

    Delegates to django_tenants' own helper, which reads `pg_catalog.pg_namespace`.
    This used to query `information_schema.schemata`, and that was a latent
    outage waiting for a stricter database role: per Postgres' documentation
    that view lists only the schemas *owned by a currently enabled role*, so an
    application connecting as a role that did not own the tenant schemas would
    see none of them. While this answer only decided whether the console could
    read a boutique, the cost of being wrong was one screen saying "unreadable".
    Now that the same answer gates EVERY schema switch in the application
    (tenants/schema_guard.py), being wrong would refuse every tenant on the
    platform. pg_namespace lists schemas regardless of ownership.

    Using the library's own function also means this cannot disagree with the
    check `TenantMixin.create_schema` makes when it decides a schema is already
    there.

    The cache is ours and is positive-only: a schema that is missing now may be
    created a moment later by a signup, and caching "absent" would make the new
    boutique invisible until the worker restarted.
    """
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
    """Drop a schema from the presence cache. Call after force_drop."""
    _present.discard(schema_name)


class MissingSchema(Exception):
    """A tenant row exists but its schema does not."""


def tenant_scope(tenant):
    """A context manager that enters `tenant`'s schema, or refuses.

    Raises MissingSchema rather than entering, which turns the silent
    public-schema fallthrough described above into something a caller must
    handle. Callers that iterate boutiques should catch it and record the
    boutique as unreadable; callers that mutate should let it propagate, because
    a write to the wrong schema is not something to continue past.
    """
    if not schema_exists(tenant.schema_name):
        raise MissingSchema(
            f"Boutique '{tenant.schema_name}' has a registry row but no database "
            f"schema. Refusing to run against it, because Postgres would silently "
            f"resolve the query against the public schema instead."
        )
    return tenant_context(tenant)


def for_each_tenant(tenants, read):
    """Run `read(tenant)` inside each boutique's schema. Returns (results, unreadable).

    `read` is called with the connection already pointed at that boutique, and
    whatever it returns is collected. A boutique that cannot be read is named in
    `unreadable` instead, because one broken boutique must not take a console
    page down -- a broken boutique is why the page was opened.

    A callback rather than a generator on purpose. The obvious shape here is to
    yield from inside the `with`, and it is wrong in a way that is easy to miss:
    an exception raised in the *caller's* loop body is delivered to the
    generator as GeneratorExit, which `except Exception` does not catch, so the
    error handling reads as if it covers the loop body and does not. Passing the
    work in means there is one frame and one try.

    Each call runs in its own savepoint. Without one, a failed query inside an
    enclosing atomic() leaves the connection aborted and every later statement
    in that transaction fails with "current transaction is aborted" -- turning
    one unreadable boutique into a completely failed request, the exact opposite
    of what the try/except was written to achieve.
    """
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
    """Enter the public schema explicitly.

    Named rather than assumed. With CONN_MAX_AGE > 0 a reused connection still
    carries whatever schema the previous request left it pointed at, so code
    that writes a public-schema model without saying so is relying on the last
    request having been a console one.
    """
    from django_tenants.utils import get_public_schema_name
    return schema_context(get_public_schema_name())
