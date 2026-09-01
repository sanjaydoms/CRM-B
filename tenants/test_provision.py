"""The clone-based fast provisioning, exercised for real.

One TransactionTestCase and one expensive fixture: `ensure_base_schema` builds
the template schema by actually migrating it (the same work production pays
once), and every test then runs against that base. Ordered test methods share
it via setUpClass rather than rebuilding per test.

What must never regress here:
  * a clone is indistinguishable from a migrated schema (ledger identical,
    seed rows present, no residents),
  * the clone participates in signup's all-or-nothing transaction,
  * the command is idempotent.
"""

from django.conf import settings
from django.core.management import call_command
from django.db import connection, transaction
from django.test import TransactionTestCase

from tenants.models import BoutiqueTenant
from tenants.provision import base_is_ready, provision_tenant


def _one(sql, params=None):
    with connection.cursor() as c:
        c.execute(sql, params or [])
        row = c.fetchone()
    return row[0] if row else None


def _count(schema, table):
    return _one(f'SELECT count(*) FROM "{schema}"."{table}"')


class CloneProvisionTests(TransactionTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        call_command('ensure_base_schema')

    def setUp(self):
        # The between-test flush wipes the base's registry row, and
        # base_is_ready deliberately requires it. Re-running the command is
        # the cheap adopt branch (insert row, no-op migrate), and makes every
        # test's provisioning path independent of run order.
        call_command('ensure_base_schema')

    def tearDown(self):
        # The framework's between-test flush introspects on the current
        # search_path; make sure a test can't leave it on a tenant schema.
        connection.set_schema_to_public()

    @classmethod
    def tearDownClass(cls):
        # Leave no template behind: a surviving tenant_base would silently
        # flip every later suite's signups onto the clone path, and --keepdb
        # reruns would clone a base staler than the code under test.
        connection.set_schema_to_public()
        with connection.cursor() as c:
            c.execute(f'DROP SCHEMA IF EXISTS "{settings.TENANT_BASE_SCHEMA}" CASCADE')
        BoutiqueTenant.objects.filter(
            schema_name=settings.TENANT_BASE_SCHEMA).delete()
        super().tearDownClass()

    def test_base_schema_is_provisioned_and_inert(self):
        base = settings.TENANT_BASE_SCHEMA
        self.assertTrue(base_is_ready())
        # Fully migrated: the ledger is populated and the newest signup-critical
        # column is present (the one whose absence broke real boutiques).
        self.assertGreater(_count(base, 'django_migrations'), 80)
        self.assertEqual(
            _one("SELECT count(*) FROM information_schema.columns WHERE "
                 "table_schema = %s AND table_name = 'crm_api_boutiquesettings' "
                 "AND column_name = 'design_approval_required'", [base]), 1)
        # Seeded: the twelve shipped garment templates are data migrations'
        # output and must ride along into every clone.
        self.assertGreater(_count(base, 'catalog_garmenttemplate'), 0)
        # Inert: nobody can ever sign in to the template.
        self.assertEqual(_count(base, 'auth_user'), 0)
        # The flush between TransactionTestCases empties public tables, so the
        # registry row is checked right after the command that (re)creates it.
        row = BoutiqueTenant.objects.get(schema_name=base)
        self.assertFalse(row.is_active)
        # The clone function the fast path calls is installed.
        self.assertEqual(
            _one("SELECT count(*) FROM pg_proc WHERE proname = 'clone_schema'"), 1)

    def test_clone_matches_migrated_schema(self):
        base = settings.TENANT_BASE_SCHEMA
        self.assertTrue(base_is_ready())  # pin the path this test exercises
        with transaction.atomic():
            tenant = provision_tenant(
                schema_name='clonecheck_fast', owner_email='clone@check.test',
                name='Clone Check')
        try:
            self.assertEqual(tenant.schema_name, 'clonecheck_fast')
            # The ledger came across whole: a deploy's migrate_schemas will
            # find nothing to do, and no "already exists" can ever surface.
            self.assertEqual(_count('clonecheck_fast', 'django_migrations'),
                             _count(base, 'django_migrations'))
            self.assertEqual(_count('clonecheck_fast', 'catalog_garmenttemplate'),
                             _count(base, 'catalog_garmenttemplate'))
            self.assertEqual(_count('clonecheck_fast', 'auth_user'), 0)
            # Sequences were advanced past the cloned rows: the next generated
            # id must not collide with one that came across in the copy.
            # django_migrations is the probe because it is guaranteed both
            # serial-keyed and populated in every clone.
            next_id = _one("SELECT nextval(pg_get_serial_sequence("
                           "'clonecheck_fast.django_migrations', 'id'))")
            max_id = _one('SELECT max(id) FROM '
                          '"clonecheck_fast"."django_migrations"')
            self.assertGreater(next_id, max_id)
        finally:
            # Both halves, always: a schema-less registry row is exactly the
            # state the schema guard exists to refuse, and it would poison the
            # next --keepdb run's test-database bootstrap.
            with connection.cursor() as c:
                c.execute('DROP SCHEMA IF EXISTS "clonecheck_fast" CASCADE')
            BoutiqueTenant.objects.filter(schema_name='clonecheck_fast').delete()

    def test_failed_signup_rolls_back_clone_completely(self):
        self.assertTrue(base_is_ready())  # the rollback under test is the clone's
        class Boom(Exception):
            pass
        try:
            with transaction.atomic():
                provision_tenant(
                    schema_name='clonecheck_doomed', owner_email='doomed@check.test',
                    name='Doomed')
                raise Boom
        except Boom:
            pass
        from django_tenants.utils import schema_exists
        self.assertFalse(schema_exists('clonecheck_doomed'))
        self.assertFalse(
            BoutiqueTenant.objects.filter(schema_name='clonecheck_doomed').exists())

    def test_ensure_base_schema_is_idempotent(self):
        before = _count(settings.TENANT_BASE_SCHEMA, 'django_migrations')
        # setUp already exercised the adopt-an-orphaned-schema branch; these
        # two calls are the steady-state branch every deploy re-runs.
        call_command('ensure_base_schema')
        call_command('ensure_base_schema')
        self.assertEqual(
            _count(settings.TENANT_BASE_SCHEMA, 'django_migrations'), before)
        self.assertEqual(
            BoutiqueTenant.objects.filter(
                schema_name=settings.TENANT_BASE_SCHEMA).count(), 1)

    def test_slow_path_still_works_when_base_absent(self):
        from django.test import override_settings
        from django_tenants.utils import schema_exists
        # Point the setting at a base that does not exist: provision_tenant
        # must fall back to CREATE SCHEMA + full migrate, because this is what
        # production runs until ensure_base_schema has been executed there.
        with override_settings(TENANT_BASE_SCHEMA='clonecheck_no_base'):
            self.assertFalse(base_is_ready())
            with transaction.atomic():
                provision_tenant(
                    schema_name='clonecheck_slow', owner_email='slow@check.test',
                    name='Slow Path')
        try:
            self.assertTrue(schema_exists('clonecheck_slow'))
            # The migrated schema and the cloned template must agree on what
            # "fully migrated" means.
            self.assertEqual(_count('clonecheck_slow', 'django_migrations'),
                             _count(settings.TENANT_BASE_SCHEMA, 'django_migrations'))
        finally:
            connection.set_schema_to_public()
            with connection.cursor() as c:
                c.execute('DROP SCHEMA IF EXISTS "clonecheck_slow" CASCADE')
            BoutiqueTenant.objects.filter(schema_name='clonecheck_slow').delete()
