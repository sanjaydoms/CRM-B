
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
        entry = audit.record(a_request(), 'console.login_failed', target='mallory')
        self.assertEqual(entry.actor, '')
        self.assertEqual(entry.target, 'mallory')

    def test_an_over_long_user_agent_is_clipped_not_dropped(self):
        entry = audit.record(a_request(self.admin, HTTP_USER_AGENT='x' * 900),
                             'data.view', target='crm_api.order')
        self.assertIsNotNone(entry, 'a long header must not cost us the entry')
        self.assertEqual(len(entry.user_agent), 300)

    def test_writes_to_public_even_from_inside_a_tenant_schema(self):
        with connection.cursor() as cursor:
            cursor.execute('CREATE SCHEMA IF NOT EXISTS "no_such_boutique_schema"')
        self.addCleanup(_drop_bare_schema, 'no_such_boutique_schema')

        with schema_context('no_such_boutique_schema'):
            entry = audit.record(a_request(self.admin), 'user.deactivate',
                                 target='cutter@acme.test', boutique='acme')
        self.assertIsNotNone(entry)
        self.assertEqual(AuditLog.objects.filter(pk=entry.pk).count(), 1)


class FailureTests(TestCase):

    def test_a_broken_write_does_not_raise(self):
        with mock.patch.object(AuditLog.objects, 'create',
                               side_effect=OperationalError('server closed the connection')):
            with self.assertLogs('superadmin.audit', level='ERROR'):
                result = audit.record(a_request(), 'boutique.suspend', target='acme')
        self.assertIsNone(result, 'a failed write reports itself as None')

    def test_a_broken_write_is_not_silent(self):
        with mock.patch.object(AuditLog.objects, 'create',
                               side_effect=OperationalError('boom')):
            with self.assertLogs('superadmin.audit', level='ERROR') as logged:
                audit.record(a_request(), 'boutique.suspend', target='acme')
        self.assertIn('audit write failed', logged.output[0])
        self.assertIn('OperationalError', logged.output[0], 'traceback is logged too')


class ClientAddressTests(TestCase):

    def test_takes_the_last_forwarded_entry(self):
        entry = audit.record(
            a_request(HTTP_X_FORWARDED_FOR='1.2.3.4, 198.51.100.9',
                      REMOTE_ADDR='10.0.0.1'),
            'console.login')
        self.assertEqual(entry.ip, '198.51.100.9')

    def test_junk_header_falls_back_to_the_peer(self):
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
        self.assertIsInstance(audit.recent(), list)
