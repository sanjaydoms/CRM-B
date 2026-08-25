"""The audit trail's two promises: it records, and it never takes the caller down.

TestCase rather than TransactionTestCase, deliberately. The rest of this app's
tests need real tenant schemas, which is DDL, which is why superadmin/tests.py
is TransactionTestCase throughout. Nothing here creates a schema: AuditLog lives
in public, the test database already has it, and the one test that needs the
connection pointed somewhere else points it at a schema that does not exist --
which is a `SET search_path`, not DDL. That keeps these in a transaction that
rolls back, which is several seconds a run rather than a truncate of every table.
"""

from unittest import mock

from django.contrib.auth.models import AnonymousUser, User
from django.db import OperationalError
from django.db import connection
from django.test import RequestFactory, TestCase
from django_tenants.utils import schema_context

from . import audit
from .models import AuditLog


def a_request(user=None, **meta):
    request = RequestFactory().post('/api/superadmin/boutiques/acme/suspend/', **meta)
    request.user = AnonymousUser() if user is None else user
    return request


def _drop_bare_schema(schema_name):
    connection.set_schema_to_public()
    with connection.cursor() as cursor:
        cursor.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema_name)
    from superadmin.schemas import forget
    forget(schema_name)


class RecordTests(TestCase):
    """What lands in the table."""

    def setUp(self):
        self.admin = User(username='platform@admin.test', is_superuser=True)

    def test_writes_the_entry(self):
        entry = audit.record(
            a_request(self.admin, REMOTE_ADDR='203.0.113.7',
                      HTTP_USER_AGENT='Mozilla/5.0 (console)'),
            'boutique.suspend', target='acme', boutique='acme',
            before={'is_active': True}, after={'is_active': False},
            reason='non-payment',
        )
        self.assertIsNotNone(entry)

        stored = AuditLog.objects.get(pk=entry.pk)
        self.assertEqual(stored.actor, 'platform@admin.test')
        self.assertEqual(stored.action, 'boutique.suspend')
        self.assertEqual(stored.target, 'acme')
        self.assertEqual(stored.boutique, 'acme')
        self.assertEqual(stored.before, {'is_active': True})
        self.assertEqual(stored.after, {'is_active': False})
        self.assertEqual(stored.reason, 'non-payment')
        self.assertEqual(stored.ip, '203.0.113.7')
        self.assertEqual(stored.user_agent, 'Mozilla/5.0 (console)')

    def test_anonymous_actor_is_blank_rather_than_missing(self):
        """console.login_failed has no authenticated user, and is exactly the
        entry you least want dropped -- the attempted name goes in `target`."""
        entry = audit.record(a_request(), 'console.login_failed', target='mallory')
        self.assertEqual(entry.actor, '')
        self.assertEqual(entry.target, 'mallory')

    def test_an_over_long_user_agent_is_clipped_not_dropped(self):
        entry = audit.record(a_request(self.admin, HTTP_USER_AGENT='x' * 900),
                             'data.view', target='crm_api.order')
        self.assertIsNotNone(entry, 'a long header must not cost us the entry')
        self.assertEqual(len(entry.user_agent), 300)

    def test_writes_to_public_even_from_inside_a_tenant_schema(self):
        """The failure this guards is silent: a console view that reaches into a
        boutique's schema and records from inside that block would aim the
        INSERT at a schema with no superadmin_auditlog in it, and record()'s own
        except would swallow the result. The schema below deliberately does not
        exist -- Postgres accepts it in search_path and fails only on the query,
        which is precisely the situation being tested."""
        # A real but EMPTY schema. This used to name one that did not exist;
        # tenants/schema_guard.py now refuses that, because Postgres resolves
        # such a query against `public` and the fallthrough was exploitable.
        # An empty schema tests the same thing -- record() must pin to public
        # from a connection pointed at a boutique that has no auditlog table --
        # and is a state a half-migrated boutique really reaches.
        with connection.cursor() as cursor:
            cursor.execute('CREATE SCHEMA IF NOT EXISTS "no_such_boutique_schema"')
        self.addCleanup(_drop_bare_schema, 'no_such_boutique_schema')

        with schema_context('no_such_boutique_schema'):
            entry = audit.record(a_request(self.admin), 'user.deactivate',
                                 target='cutter@acme.test', boutique='acme')
        self.assertIsNotNone(entry)
        self.assertEqual(AuditLog.objects.filter(pk=entry.pk).count(), 1)


class FailureTests(TestCase):
    """What happens when the table is not there.

    Mocked rather than acted out by dropping the table: dropping it is DDL, and
    it would force this whole file into TransactionTestCase to test a branch
    that only cares that *something* raised.
    """

    def test_a_broken_write_does_not_raise(self):
        with mock.patch.object(AuditLog.objects, 'create',
                               side_effect=OperationalError('server closed the connection')):
            with self.assertLogs('superadmin.audit', level='ERROR'):
                result = audit.record(a_request(), 'boutique.suspend', target='acme')
        self.assertIsNone(result, 'a failed write reports itself as None')

    def test_a_broken_write_is_not_silent(self):
        """The other half of the promise. An audit trail that stops recording
        and says nothing still looks authoritative, which is worse than none."""
        with mock.patch.object(AuditLog.objects, 'create',
                               side_effect=OperationalError('boom')):
            with self.assertLogs('superadmin.audit', level='ERROR') as logged:
                audit.record(a_request(), 'boutique.suspend', target='acme')
        self.assertIn('audit write failed', logged.output[0])
        self.assertIn('OperationalError', logged.output[0], 'traceback is logged too')


class ClientAddressTests(TestCase):
    """X-Forwarded-For, which is client-supplied and therefore hostile input.

    record() reuses tenants.views._client_ip rather than restating the rules;
    these assert the behaviour through record(), because what matters here is
    that the entry survives whatever the header contains.
    """

    def test_takes_the_last_forwarded_entry(self):
        """Render appends the real peer, so the last entry is the honest one.
        The leftmost -- the usual choice -- is the one the caller controls."""
        entry = audit.record(
            a_request(HTTP_X_FORWARDED_FOR='1.2.3.4, 198.51.100.9',
                      REMOTE_ADDR='10.0.0.1'),
            'console.login')
        self.assertEqual(entry.ip, '198.51.100.9')

    def test_junk_header_falls_back_to_the_peer(self):
        """The column is a Postgres inet and Django hands it the value unparsed,
        so an unvalidated header used to be a 500. Falling back rather than
        giving up is what keeps the recorded address meaningful."""
        entry = audit.record(
            a_request(HTTP_X_FORWARDED_FOR='notanip; DROP TABLE',
                      REMOTE_ADDR='198.51.100.22'),
            'console.login')
        self.assertIsNotNone(entry)
        self.assertEqual(entry.ip, '198.51.100.22')

    def test_junk_everywhere_still_records_the_action(self):
        entry = audit.record(
            a_request(HTTP_X_FORWARDED_FOR='<script>', REMOTE_ADDR='also-not-an-ip'),
            'console.login')
        self.assertIsNotNone(entry, 'an unknown address is not a reason to lose the entry')
        self.assertIsNone(entry.ip)


class RecentTests(TestCase):
    """The reader the console's history page uses."""

    def setUp(self):
        user = User(username='admin@a.test')
        for schema in ('acme', 'acme', 'beta'):
            audit.record(a_request(user), 'boutique.suspend',
                         target=schema, boutique=schema)
        audit.record(a_request(User(username='other@a.test')),
                     'flag.change', target='new_ui')

    def test_newest_first(self):
        entries = audit.recent()
        self.assertEqual(len(entries), 4)
        self.assertEqual(entries[0].action, 'flag.change')

    def test_filters_are_applied_in_the_database(self):
        self.assertEqual(len(audit.recent(boutique='acme')), 2)
        self.assertEqual(len(audit.recent(actor='other@a.test')), 1)
        self.assertEqual(len(audit.recent(action='boutique.suspend')), 3)

    def test_limit_is_clamped_rather_than_trusted(self):
        self.assertEqual(len(audit.recent(limit=2)), 2)
        self.assertEqual(len(audit.recent(limit=10 ** 9)), 4)

    def test_returns_a_list_not_a_lazy_queryset(self):
        """A queryset returned out of schema_context would be evaluated by the
        caller after the connection had gone back to a tenant schema."""
        self.assertIsInstance(audit.recent(), list)
