"""Provision a new boutique's schema in seconds instead of half an hour.

Signup builds a tenant schema synchronously inside the HTTP request. The
original path replays every migration -- ~200 of them, three of which insert
thousands of seed rows one statement at a time. Against a database in another
region that is 20-40 minutes of network round trips, and every client gives up
long before it finishes ("nothing is coming").

The fix: keep ONE fully migrated, fully seeded template schema
(settings.TENANT_BASE_SCHEMA), and create each new boutique by cloning it with
django-tenants' bundled `clone_schema` plpgsql function -- a single server-side
statement that copies structure, seed data AND the django_migrations ledger in
a few seconds, with no per-statement latency.

Why this module exists instead of django-tenants' own
TENANT_CREATION_FAKES_MIGRATIONS path: their CloneSchema.clone_schema() calls
`transaction.commit()` (to persist the function it may have just installed),
which raises TransactionManagementError inside the signup view's atomic block
-- and that atomic block is load-bearing: it is what guarantees a failed
signup leaves no half-built boutique behind. So the plpgsql function is
installed once by `manage.py ensure_base_schema`, and signup calls it directly
with a plain cursor: one statement, fully transactional, atomicity intact.

The fast path activates itself: it is taken exactly when the base schema
exists. No flag to flip, nothing to break in tests or local dev where the base
has not been provisioned. The base stays current because it is registered as
an ordinary (inactive) tenant row, so every deploy's migrate_schemas visits it
-- which means a clone can never be behind the code that serves it.

django-tenants' own TENANT_CREATION_FAKES_MIGRATIONS setting must stay unset:
setting it would route every other `BoutiqueTenant.save()` through their
commit-inside-atomic clone path.
"""

from django.conf import settings
from django.db import connection

from tenants.models import BoutiqueTenant

# The identity of the template registry row. The address is unroutable by
# construction (.invalid, RFC 2606) so it can never collide with a signup.
BASE_OWNER_EMAIL = 'tenant-base@platform.invalid'
BASE_NAME = '(template schema - do not use)'


def base_is_ready():
    """Whether the fast path is available: template schema AND registry row.

    The row is required, not just the schema, because the row is what makes
    every deploy's migrate_schemas keep the base current. A schema whose row
    was deleted would still clone -- an ever-staler template, silently, every
    boutique born missing whatever shipped since. Requiring both means that
    state falls back to the slow-but-correct path instead.
    """
    from django_tenants.utils import schema_exists
    return (schema_exists(settings.TENANT_BASE_SCHEMA)
            and BoutiqueTenant.objects.filter(
                schema_name=settings.TENANT_BASE_SCHEMA).exists())


def provision_tenant(**fields):
    """Create a BoutiqueTenant and its schema; clone when the base is ready.

    Runs inside the caller's transaction on purpose -- the clone is one
    statement, so a failure anywhere later in signup rolls back the schema,
    the registry row and everything in between, exactly like the slow path.

    A missing clone_schema function or a vanished base schema raises loudly
    and rolls back. Deliberately NO silent fallback to the migration path:
    that would turn a broken base into 30-minute signups nobody notices.
    """
    tenant = BoutiqueTenant(**fields)
    if base_is_ready():
        tenant.auto_create_schema = False
        tenant.save()
        with connection.cursor() as cursor:
            # Serialize against a deploy migrating the base mid-clone. Every
            # migration records itself in the base's ledger (ROW EXCLUSIVE),
            # which conflicts with SHARE -- so a clone sees a consistent
            # pre- or post-migration base, never a half-migrated one whose
            # copied ledger would lie forever. Held until signup commits,
            # which is seconds now. A deadlock between the two is possible
            # and benign: Postgres aborts one side loudly, the atomic block
            # rolls back whole, and a retry succeeds.
            cursor.execute(
                'LOCK TABLE "%s".django_migrations IN SHARE MODE'
                % settings.TENANT_BASE_SCHEMA)
            # Same call shape CloneSchema uses; 'DATA' copies seed rows and
            # the django_migrations ledger along with the structure.
            cursor.execute(
                'SELECT clone_schema(%s, %s, %s)',
                [settings.TENANT_BASE_SCHEMA, tenant.schema_name, 'DATA'],
            )
    else:
        # Slow path: CREATE SCHEMA + full migrate, as before this module.
        tenant.save()
    return tenant


def install_clone_function():
    """Create or refresh the clone_schema plpgsql function.

    django-tenants' own installer substitutes settings.DATABASES USER into
    `ALTER FUNCTION ... OWNER TO` -- and on Supabase's pooler that USER is the
    supavisor login ('postgres.<project-ref>'), a routing name that is not a
    Postgres role, so the install fails after the whole base build succeeded.
    Asking the server for `current_user` names the role the connection really
    runs as, everywhere. Same function body, same grants.
    """
    from django_tenants.clone import CLONE_SCHEMA_FUNCTION
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_user')
        role = cursor.fetchone()[0]
        cursor.execute(CLONE_SCHEMA_FUNCTION.format(db_user=role))
