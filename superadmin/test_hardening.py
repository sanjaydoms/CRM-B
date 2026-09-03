
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection
from django.test import TransactionTestCase
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from crm_api.models import Customer
from superadmin import datasets
from superadmin.models import AuditLog
from superadmin.test_users_search import ghost_tenant
from superadmin.tests import temporary_tenant
from tenants.middleware import clear_tenant_cache
from tenants.models import BoutiqueTenant


def platform_admin(username='harden@admin.test', password='harden-admin-pw-1'):

    connection.set_schema_to_public()
    User.objects.filter(username=username).delete()
    User.objects.create_superuser(username=username, email=username, password=password)
    client = APIClient()
    response = client.post('/api/superadmin/auth/login/',
                           {'username': username, 'password': password}, format='json')
    assert response.status_code == 200, response.content
    client.credentials(HTTP_AUTHORIZATION='Token ' + response.json()['token'])
    return client


def boutique_client(schema_name, username, password='boutique-pw-1'):

    with schema_context(schema_name):
        user = User.objects.create_user(username=username, email=username,
                                        password=password)
        key = Token.objects.get_or_create(user=user)[0].key
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION='Token ' + key,
                       HTTP_X_TENANT_ID=schema_name)
    return client


class ControlStateIsAuthoritative(TransactionTestCase):

    def setUp(self):
        connection.set_schema_to_public()
        cache.clear()
        clear_tenant_cache()

    def test_a_suspension_takes_effect_without_clearing_any_cache(self):
        with temporary_tenant('hard_susp', 'o@hard.test', 'Hardened') as tenant:
            client = boutique_client('hard_susp', 'u@hard.test')

            self.assertEqual(
                client.get('/api/customers/', HTTP_X_TENANT_ID='hard_susp').status_code, 200)

            BoutiqueTenant.objects.filter(pk=tenant.pk).update(is_active=False)

            refused = client.get('/api/customers/', HTTP_X_TENANT_ID='hard_susp')
            self.assertEqual(refused.status_code, 403, 'a suspended boutique was served')
            self.assertIn('suspended', refused.json()['error'])

    def test_reactivation_is_symmetric_and_equally_immediate(self):
        with temporary_tenant('hard_react', 'o@react.test', 'Reactivated') as tenant:
            client = boutique_client('hard_react', 'u@react.test')

            BoutiqueTenant.objects.filter(pk=tenant.pk).update(is_active=False)
            self.assertEqual(
                client.get('/api/customers/', HTTP_X_TENANT_ID='hard_react').status_code, 403)

            BoutiqueTenant.objects.filter(pk=tenant.pk).update(is_active=True)
            self.assertEqual(
                client.get('/api/customers/', HTTP_X_TENANT_ID='hard_react').status_code, 200,
                'a reactivated boutique was still locked out')

    def test_a_module_switch_takes_effect_without_clearing_any_cache(self):

        with temporary_tenant('hard_mod', 'o@mod.test', 'Modules') as tenant:
            client = boutique_client('hard_mod', 'u@mod.test')
            self.assertEqual(
                client.get('/api/fabrics/', HTTP_X_TENANT_ID='hard_mod').status_code, 200)

            BoutiqueTenant.objects.filter(pk=tenant.pk).update(
                enabled_modules={'fabrics': False})

            refused = client.get('/api/fabrics/', HTTP_X_TENANT_ID='hard_mod')
            self.assertEqual(refused.status_code, 403, 'a disabled module was served')
            self.assertEqual(refused.json()['module'], 'fabrics')

            self.assertEqual(
                client.get('/api/fabrics.json', HTTP_X_TENANT_ID='hard_mod').status_code, 403)

    def test_a_deleted_registry_row_stops_being_served(self):

        tenant = None
        with temporary_tenant('hard_gone', 'o@gone.test', 'Gone') as created:
            tenant = created
            client = boutique_client('hard_gone', 'u@gone.test')
            self.assertEqual(
                client.get('/api/customers/', HTTP_X_TENANT_ID='hard_gone').status_code, 200)
        connection.set_schema_to_public()
        self.assertFalse(BoutiqueTenant.objects.filter(pk=tenant.pk).exists())

        after = APIClient().get('/api/customers/', HTTP_X_TENANT_ID='hard_gone')
        self.assertIn(after.status_code, (400, 503),
                      'a deleted boutique was still resolvable from cache')


class GhostSchemaIsRefused(TransactionTestCase):

    def setUp(self):
        connection.set_schema_to_public()
        cache.clear()
        clear_tenant_cache()
        User.objects.filter(username='ghost@platform.test').delete()
        self.admin = User.objects.create_superuser(
            username='ghost@platform.test', email='ghost@platform.test',
            password='platform-pw-4242')
        self.admin_token = Token.objects.get_or_create(user=self.admin)[0]

    def test_a_public_token_is_never_bound_to_a_ghost_boutique(self):
        with ghost_tenant('hard_ghost1', 'o@g1.test', 'Ghost One'):
            clear_tenant_cache()
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION='Token ' + self.admin_token.key)
            response = client.get('/api/auth/me/')

            if response.status_code == 200:
                self.assertNotEqual(
                    response.json().get('tenant_id'), 'hard_ghost1',
                    'the platform administrator was bound to a boutique with no schema')

    def test_naming_a_ghost_boutique_is_refused_rather_than_resolved(self):
        with ghost_tenant('hard_ghost2', 'o@g2.test', 'Ghost Two'):
            clear_tenant_cache()
            response = APIClient().get('/api/customers/', HTTP_X_TENANT_ID='hard_ghost2')
            self.assertEqual(response.status_code, 503,
                             'a boutique with no schema was resolved')
            self.assertNotIn('does not exist', response.content.decode(),
                             'the raw Postgres error reached the caller')

    def test_reads_and_writes_across_every_module_are_refused_alike(self):
        with ghost_tenant('hard_ghost3', 'o@g3.test', 'Ghost Three'):
            clear_tenant_cache()
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION='Token ' + self.admin_token.key,
                               HTTP_X_TENANT_ID='hard_ghost3')

            reads = ['/api/customers/', '/api/orders/', '/api/fabrics/',
                     '/api/tailors/', '/api/inventory/items/',
                     '/api/design-studio/designs/', '/api/production/tasks/',
                     '/api/scheduling/appointments/', '/api/dashboard/']
            for url in reads:
                self.assertEqual(client.get(url).status_code, 503, f'GET {url}')

            writes = [('/api/customers/', {'first_name': 'X', 'last_name': 'Y',
                                           'mobile_number': '9000000009'}),
                      ('/api/fabrics/', {'name': 'F', 'material': 'silk'}),
                      ('/api/tailors/', {'name': 'T', 'specialty': 'blouse'})]
            for url, payload in writes:
                self.assertEqual(client.post(url, payload, format='json').status_code,
                                 503, f'POST {url}')

            connection.set_schema_to_public()
            self.assertTrue(User.objects.get(pk=self.admin.pk).is_active)
            self.assertTrue(Token.objects.filter(pk=self.admin_token.pk).exists())

    def test_a_ghost_boutique_cannot_authenticate_the_platform_account(self):
        with ghost_tenant('hard_ghost4', 'o@g4.test', 'Ghost Four'):
            clear_tenant_cache()
            response = APIClient().post(
                '/api/auth/login/',
                {'username': 'ghost@platform.test', 'password': 'platform-pw-4242'},
                format='json')
            self.assertNotEqual(response.status_code, 200,
                                'the platform account signed in as a boutique user')
            if response.status_code == 200:  # pragma: no cover - guarded above
                self.assertNotEqual(response.json().get('tenant_id'), 'hard_ghost4')

    def test_a_real_boutique_is_unaffected_by_a_ghost_beside_it(self):

        with temporary_tenant('hard_real', 'o@real.test', 'Real'), \
             ghost_tenant('hard_ghost5', 'o@g5.test', 'Ghost Five'):
            clear_tenant_cache()
            client = boutique_client('hard_real', 'u@real.test')
            self.assertEqual(
                client.get('/api/customers/', HTTP_X_TENANT_ID='hard_real').status_code, 200)


class DataBrowserIsAudited(TransactionTestCase):

    def setUp(self):
        connection.set_schema_to_public()
        cache.clear()
        AuditLog.objects.all().delete()

    def _entries(self, action='data.view'):
        connection.set_schema_to_public()
        return list(AuditLog.objects.filter(action=action))

    def test_reading_a_boutiques_customers_is_recorded(self):
        with temporary_tenant('hard_audit', 'o@audit.test', 'Audited'):
            with schema_context('hard_audit'):
                Customer.objects.create(first_name='Priya', last_name='R',
                                        mobile_number='9000000001')
            client = platform_admin()
            AuditLog.objects.all().delete()

            response = client.get(
                '/api/superadmin/boutiques/hard_audit/data/crm_api.customer/')
            self.assertEqual(response.status_code, 200)
            self.assertIn('Priya', response.content.decode())

            entries = self._entries()
            self.assertEqual(len(entries), 1, 'the read left no trail')
            entry = entries[0]
            self.assertEqual(entry.actor, 'harden@admin.test')
            self.assertEqual(entry.boutique, 'hard_audit')
            self.assertEqual(entry.target, 'crm_api.customer')
            self.assertEqual(entry.after['access'], 'rows')
            self.assertEqual(entry.after['rows'], 1)
            self.assertIsNotNone(entry.ip)

    def test_the_table_index_is_a_distinct_recorded_access(self):
        with temporary_tenant('hard_audit2', 'o@audit2.test', 'Audited Two'):
            client = platform_admin()
            AuditLog.objects.all().delete()

            self.assertEqual(
                client.get('/api/superadmin/boutiques/hard_audit2/data/').status_code, 200)
            entries = self._entries()
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].after['access'], 'model_index')

    def test_a_search_records_what_was_searched_for(self):
        with temporary_tenant('hard_audit3', 'o@audit3.test', 'Audited Three'):
            with schema_context('hard_audit3'):
                Customer.objects.create(first_name='Meera', last_name='S',
                                        mobile_number='9000000002')
            client = platform_admin()
            AuditLog.objects.all().delete()

            client.get('/api/superadmin/boutiques/hard_audit3/data/'
                       'crm_api.customer/?q=Meera')
            entry = self._entries()[0]
            self.assertEqual(entry.after['search'], 'Meera')

            AuditLog.objects.all().delete()
            client.get('/api/superadmin/boutiques/hard_audit3/data/'
                       'crm_api.customer/?q=' + 'z' * 400)
            self.assertLessEqual(
                len(self._entries()[0].after['search']),
                __import__('superadmin.views', fromlist=['x'])
                .BoutiqueDataView.SEARCH_TERM_LIMIT)

    def test_naming_a_table_the_console_will_not_serve_is_recorded(self):

        with temporary_tenant('hard_audit4', 'o@audit4.test', 'Audited Four'):
            client = platform_admin()
            AuditLog.objects.all().delete()

            response = client.get(
                '/api/superadmin/boutiques/hard_audit4/data/authtoken.token/')
            self.assertEqual(response.status_code, 404)
            entry = self._entries()[0]
            self.assertEqual(entry.after['access'], 'refused')
            self.assertEqual(entry.target, 'authtoken.token')


class DataBrowserAllowlist(TransactionTestCase):

    def setUp(self):
        connection.set_schema_to_public()
        cache.clear()

    def test_a_field_nobody_has_reviewed_is_masked(self):
        with temporary_tenant('hard_allow', 'o@allow.test', 'Allowlisted'):
            with schema_context('hard_allow'):
                Customer.objects.create(first_name='Anita', last_name='K',
                                        mobile_number='9000000003',
                                        address='12 Residency Road')
            client = platform_admin()

            original = datasets.ALLOWED_FIELDS['crm_api.customer']
            datasets.ALLOWED_FIELDS['crm_api.customer'] = tuple(
                f for f in original if f != 'address')
            try:
                body = client.get('/api/superadmin/boutiques/hard_allow/data/'
                                  'crm_api.customer/').json()
            finally:
                datasets.ALLOWED_FIELDS['crm_api.customer'] = original

            row = body['rows'][0]
            self.assertEqual(row['address'], datasets.REDACTED,
                             'an unreviewed column was rendered')
            self.assertTrue(next(c for c in body['columns']
                                 if c['name'] == 'address')['redacted'])
            self.assertEqual(row['first_name'], 'Anita')

    def test_a_model_nobody_has_reviewed_is_not_browsable(self):

        with temporary_tenant('hard_allow2', 'o@allow2.test', 'Allowlisted Two'):
            client = platform_admin()

            original = datasets.ALLOWED_FIELDS.pop('crm_api.customer')
            try:
                listing = client.get(
                    '/api/superadmin/boutiques/hard_allow2/data/').json()
                self.assertNotIn('crm_api.customer',
                                 [d['key'] for d in listing['datasets']])
                self.assertEqual(
                    client.get('/api/superadmin/boutiques/hard_allow2/data/'
                               'crm_api.customer/').status_code, 404)
            finally:
                datasets.ALLOWED_FIELDS['crm_api.customer'] = original

    def test_a_masked_column_cannot_be_searched(self):
        with temporary_tenant('hard_allow3', 'o@allow3.test', 'Allowlisted Three'):
            with schema_context('hard_allow3'):
                Customer.objects.create(first_name='Ravi', last_name='M',
                                        mobile_number='9000000004',
                                        address='7 Secret Lane')
            client = platform_admin()

            original = datasets.ALLOWED_FIELDS['crm_api.customer']
            datasets.ALLOWED_FIELDS['crm_api.customer'] = tuple(
                f for f in original if f != 'address')
            try:
                body = client.get('/api/superadmin/boutiques/hard_allow3/data/'
                                  'crm_api.customer/?q=Secret').json()
            finally:
                datasets.ALLOWED_FIELDS['crm_api.customer'] = original

            self.assertEqual(body['count'], 0,
                             'a masked column answered a search and became an oracle')

    def test_the_password_hash_stays_masked_by_both_rules(self):
        with temporary_tenant('hard_allow4', 'o@allow4.test', 'Allowlisted Four'):
            with schema_context('hard_allow4'):
                User.objects.create_user(username='staff@allow4.test',
                                         password='a-password-to-hash')
            client = platform_admin()

            original = datasets.ALLOWED_FIELDS['auth.user']
            datasets.ALLOWED_FIELDS['auth.user'] = original + ('password',)
            try:
                body = client.get('/api/superadmin/boutiques/hard_allow4/data/'
                                  'auth.user/').content.decode()
            finally:
                datasets.ALLOWED_FIELDS['auth.user'] = original

            self.assertNotIn('pbkdf2', body)
            self.assertNotIn('a-password-to-hash', body)

    def test_every_allowlisted_field_still_exists_on_its_model(self):
        from django.apps import apps

        stale = []
        for key, allowed in datasets.ALLOWED_FIELDS.items():
            try:
                model = apps.get_model(key)
            except LookupError:
                stale.append(f'{key} (no such model)')
                continue
            real = {f.name for f in model._meta.concrete_fields}
            for name in allowed:
                if name not in real:
                    stale.append(f'{key}.{name}')
        self.assertEqual(stale, [], 'ALLOWED_FIELDS names fields that do not exist:\n'
                                    + '\n'.join(stale))


class ConsoleSessionsAreAudited(TransactionTestCase):

    def setUp(self):
        connection.set_schema_to_public()
        cache.clear()
        AuditLog.objects.all().delete()

    def test_a_successful_sign_in_is_recorded(self):
        platform_admin(username='session@admin.test')
        connection.set_schema_to_public()
        entry = AuditLog.objects.filter(action='console.login').first()
        self.assertIsNotNone(entry, 'a console sign-in left no trace')
        self.assertEqual(entry.actor, 'session@admin.test')

    def test_a_failed_sign_in_is_recorded_without_claiming_an_actor(self):
        connection.set_schema_to_public()
        User.objects.filter(username='fail@admin.test').delete()
        User.objects.create_superuser(username='fail@admin.test',
                                      email='fail@admin.test', password='right-pw-9')
        AuditLog.objects.all().delete()

        response = APIClient().post('/api/superadmin/auth/login/',
                                    {'username': 'fail@admin.test', 'password': 'wrong'},
                                    format='json')
        self.assertEqual(response.status_code, 400)

        connection.set_schema_to_public()
        entry = AuditLog.objects.filter(action='console.login_failed').first()
        self.assertIsNotNone(entry, 'a failed console sign-in left no trace')
        self.assertEqual(entry.actor, '')
        self.assertEqual(entry.target, 'fail@admin.test')

    def test_a_failed_sign_in_for_an_unknown_account_looks_the_same(self):
        AuditLog.objects.all().delete()
        APIClient().post('/api/superadmin/auth/login/',
                         {'username': 'nobody@nowhere.test', 'password': 'x'},
                         format='json')
        connection.set_schema_to_public()
        entry = AuditLog.objects.filter(action='console.login_failed').first()
        self.assertIsNotNone(entry)
        self.assertNotIn('exist', (entry.reason or '').lower())
        self.assertIsNone(entry.after)

    def test_signing_out_is_recorded(self):
        client = platform_admin(username='out@admin.test')
        connection.set_schema_to_public()
        AuditLog.objects.all().delete()

        self.assertEqual(client.post('/api/superadmin/auth/logout/').status_code, 204)
        connection.set_schema_to_public()
        entry = AuditLog.objects.filter(action='console.logout').first()
        self.assertIsNotNone(entry, 'a console sign-out left no trace')
        self.assertEqual(entry.actor, 'out@admin.test')


class ConsoleLoginIsRateLimited(TransactionTestCase):

    def setUp(self):
        connection.set_schema_to_public()
        cache.clear()

    def test_repeated_wrong_passwords_are_eventually_refused(self):
        User.objects.filter(username='brute@admin.test').delete()
        User.objects.create_superuser(username='brute@admin.test',
                                      email='brute@admin.test', password='real-pw-77')

        codes = [APIClient().post('/api/superadmin/auth/login/',
                                  {'username': 'brute@admin.test',
                                   'password': f'guess-{i}'}, format='json').status_code
                 for i in range(30)]
        self.assertIn(429, codes, 'the console login can be guessed without limit')

    def test_the_two_login_doors_share_one_budget(self):
        User.objects.filter(username='shared@admin.test').delete()
        User.objects.create_superuser(username='shared@admin.test',
                                      email='shared@admin.test', password='real-pw-88')

        for i in range(30):
            APIClient().post('/api/superadmin/auth/login/',
                             {'username': 'shared@admin.test',
                              'password': f'guess-{i}'}, format='json')

        spent = APIClient().post('/api/auth/login/',
                                 {'username': 'someone@boutique.test',
                                  'password': 'guess'}, format='json')
        self.assertEqual(spent.status_code, 429,
                         'the boutique login handed out a fresh budget')
