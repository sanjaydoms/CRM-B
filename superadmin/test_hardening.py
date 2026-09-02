"""Regression tests for the defects found in the control-plane hardening pass.

Every test here was written against a *measured* failure, not a suspected one.
Each one fails if its defect comes back, and the docstring says what the wrong
answer looked like when it was real -- because "assertEqual(403)" on its own
does not tell the next reader what they have broken.

Four defects, in the order they matter:

  1. Suspension served from a per-worker cache, so a boutique the database said
     was switched off kept being answered 200 by a worker that had not been
     told. (ControlStateIsAuthoritative)
  2. A tenant whose Postgres schema does not exist could be bound to the
     connection, and every query then resolved against `public`. The console was
     protected; the product's own request path was not. (GhostSchemaIsRefused)
  3. The generic data browser read every row of every table in every boutique
     and wrote no audit entry, while SupportView -- which reads strictly less --
     wrote one. (DataBrowserIsAudited)
  4. Field masking was a denylist of credential-shaped names, so it protected
     only against names somebody had already thought of. (DataBrowserAllowlist)

Plus the audit vocabulary that described sign-ins nobody recorded.
(ConsoleSessionsAreAudited)
"""

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
    """A signed-in platform administrator, and a client carrying its token."""
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
    """A signed-in boutique user, and a client carrying its token.

    The account is given the boutique's OWN owner_email, whatever username the
    caller passes. These tests are about suspension, module gates and ghost
    schemas -- they need somebody the API will talk to, not a particular
    person -- and before Phase 8 any profile-less account was handed OWNER by
    default. core.roles now decides ownership positively, by matching this
    address, so the fixture has to name the owner it was relying on being.
    """
    from tenants.models import BoutiqueTenant
    connection.set_schema_to_public()
    owner_email = (BoutiqueTenant.objects
                   .filter(schema_name=schema_name)
                   .values_list('owner_email', flat=True)
                   .first()) or username
    with schema_context(schema_name):
        user = User.objects.create_user(username=username, email=owner_email,
                                        password=password)
        key = Token.objects.get_or_create(user=user)[0].key
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION='Token ' + key,
                       HTTP_X_TENANT_ID=schema_name)
    return client


class ControlStateIsAuthoritative(TransactionTestCase):
    """Suspension and module gating must not be served from a stale cache.

    The measured defect: warm one worker's tenant cache, commit `is_active=False`
    from another process, and the warm worker answered **200** for the same
    request it had just served -- for as long as _TENANT_CACHE_TTL, which is 300
    seconds. gunicorn runs two workers and the console clears only its own, so
    "boutique suspended" was true in the database and false in half of production.

    Every test below deliberately does NOT call clear_tenant_cache(). That call
    is what a second worker cannot make, and leaving it out is the whole test.
    """

    def setUp(self):
        connection.set_schema_to_public()
        cache.clear()
        clear_tenant_cache()

    def test_a_suspension_takes_effect_without_clearing_any_cache(self):
        with temporary_tenant('hard_susp', 'o@hard.test', 'Hardened') as tenant:
            client = boutique_client('hard_susp', 'u@hard.test')

            # Warms this worker's tenant cache with is_active=True.
            self.assertEqual(
                client.get('/api/customers/', HTTP_X_TENANT_ID='hard_susp').status_code, 200)

            BoutiqueTenant.objects.filter(pk=tenant.pk).update(is_active=False)

            refused = client.get('/api/customers/', HTTP_X_TENANT_ID='hard_susp')
            self.assertEqual(refused.status_code, 403, 'a suspended boutique was served')
            self.assertIn('suspended', refused.json()['error'])

    def test_reactivation_is_symmetric_and_equally_immediate(self):
        """The direction that fails open the other way.

        A reactivation that waits for a TTL leaves a paying boutique locked out
        after the administrator has been told they let them back in.
        """
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
        """enabled_modules rode the same cached object as is_active."""
        with temporary_tenant('hard_mod', 'o@mod.test', 'Modules') as tenant:
            client = boutique_client('hard_mod', 'u@mod.test')
            self.assertEqual(
                client.get('/api/fabrics/', HTTP_X_TENANT_ID='hard_mod').status_code, 200)

            BoutiqueTenant.objects.filter(pk=tenant.pk).update(
                enabled_modules={'fabrics': False})

            refused = client.get('/api/fabrics/', HTTP_X_TENANT_ID='hard_mod')
            self.assertEqual(refused.status_code, 403, 'a disabled module was served')
            self.assertEqual(refused.json()['module'], 'fabrics')

            # And the .json() spelling of the same route, which was a live
            # bypass once already (core/modules.py _normalise).
            self.assertEqual(
                client.get('/api/fabrics.json', HTTP_X_TENANT_ID='hard_mod').status_code, 403)

    def test_a_deleted_registry_row_stops_being_served(self):
        """Fail closed, rather than serving whoever is still in the cache."""
        tenant = None
        with temporary_tenant('hard_gone', 'o@gone.test', 'Gone') as created:
            tenant = created
            client = boutique_client('hard_gone', 'u@gone.test')
            self.assertEqual(
                client.get('/api/customers/', HTTP_X_TENANT_ID='hard_gone').status_code, 200)
            # The row goes; the schema is dropped with it by temporary_tenant.
        connection.set_schema_to_public()
        self.assertFalse(BoutiqueTenant.objects.filter(pk=tenant.pk).exists())

        after = APIClient().get('/api/customers/', HTTP_X_TENANT_ID='hard_gone')
        self.assertIn(after.status_code, (400, 503),
                      'a deleted boutique was still resolvable from cache')


class GhostSchemaIsRefused(TransactionTestCase):
    """A registry row with no Postgres schema must never become the connection.

    `SET search_path = 'ghost', public` does not fail -- Postgres skips the
    missing entry -- so every query lands in `public`, where `auth_user` and
    `authtoken_token` really do exist because `auth` is a SHARED_APP. Nothing
    raises, which is what makes it dangerous.

    superadmin/schemas.py closed this for the console. These tests are about the
    product's own request path, which is where the measured failure was:

        GET /api/auth/me/ carrying the PLATFORM CONSOLE's token and no
        X-Tenant-ID answered 200 and reported tenant_id = the ghost schema.

    The console's own administrator was admitted as a boutique user of a
    boutique that does not exist.
    """

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
        """The measured 200. The token scan walked into the ghost and matched
        the platform's own row, because it was really reading public."""
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
        """The guard is in the one place a tenant becomes the connection, so it
        covers orders, inventory, design, production and scheduling at once --
        rather than each caller remembering."""
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

            # And the account doing the asking is untouched. This is the
            # invariant with teeth: `auth_user` and `authtoken_token` DO exist
            # in public (auth is a SHARED_APP), so those are the tables a write
            # through a ghost schema actually lands in -- which is how a click
            # on a broken boutique once deactivated the console administrator's
            # own login. The business tables cannot be checked the same way
            # because they exist in no schema but a boutique's, which is why
            # those reads merely 500ed instead of leaking.
            connection.set_schema_to_public()
            self.assertTrue(User.objects.get(pk=self.admin.pk).is_active)
            self.assertTrue(Token.objects.filter(pk=self.admin_token.pk).exists())

    def test_a_ghost_boutique_cannot_authenticate_the_platform_account(self):
        """Login resolves its own tenant by scanning schemas, so it walked into
        the ghost too and ran authenticate() against the public auth_user."""
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
        """The guard must not cost a working boutique anything."""
        with temporary_tenant('hard_real', 'o@real.test', 'Real'), \
             ghost_tenant('hard_ghost5', 'o@g5.test', 'Ghost Five'):
            clear_tenant_cache()
            client = boutique_client('hard_real', 'u@real.test')
            self.assertEqual(
                client.get('/api/customers/', HTTP_X_TENANT_ID='hard_real').status_code, 200)


class DataBrowserIsAudited(TransactionTestCase):
    """Reading a boutique's tables through the generic browser leaves a trail.

    Measured defect: GET /boutiques/<schema>/data/crm_api.customer/ returned a
    customer's name, phone and address, and wrote **zero** audit rows -- while
    SupportView, which returns strictly less about the same boutique, wrote a
    `data.view` entry. The most powerful read surface on the platform was the
    only unlogged one.
    """

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
            # The entry must be able to say where the request came from.
            self.assertIsNotNone(entry.ip)

    def test_the_table_index_is_a_distinct_recorded_access(self):
        """Row counts per table are a real fact about someone's business even
        though no row is rendered, and 'opened the index' must be tellable from
        'read the customer table'."""
        with temporary_tenant('hard_audit2', 'o@audit2.test', 'Audited Two'):
            client = platform_admin()
            AuditLog.objects.all().delete()

            self.assertEqual(
                client.get('/api/superadmin/boutiques/hard_audit2/data/').status_code, 200)
            entries = self._entries()
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].after['access'], 'model_index')

    def test_a_search_records_what_was_searched_for(self):
        """Combing a boutique's records for one person is the access a reviewer
        most needs to see, and 'searched something' does not describe it."""
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

            # Bounded, because it is caller-supplied text going into a record.
            AuditLog.objects.all().delete()
            client.get('/api/superadmin/boutiques/hard_audit3/data/'
                       'crm_api.customer/?q=' + 'z' * 400)
            self.assertLessEqual(
                len(self._entries()[0].after['search']),
                __import__('superadmin.views', fromlist=['x'])
                .BoutiqueDataView.SEARCH_TERM_LIMIT)

    def test_naming_a_table_the_console_will_not_serve_is_recorded(self):
        """A trail holding only successful reads cannot show someone probing."""
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
    """What may be rendered is an allowlist, not a list of forbidden names.

    Measured defect: the denylist matched 'password', 'api_key', 'auth_token'
    and friends, and let 'gateway_credential', 'webhook_signing', 'otp_seed',
    'recovery_code', 'session_key' and 'pat' through untouched. It was a bet
    that every future credential would be spelled like a past one.
    """

    def setUp(self):
        connection.set_schema_to_public()
        cache.clear()

    def test_a_field_nobody_has_reviewed_is_masked(self):
        """The property being bought: a column added tomorrow is masked today.

        Simulated by taking one field back off the allowlist, which is exactly
        the state a newly added column is in.
        """
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
            # Masked, not hidden: the console still says the column is there.
            self.assertTrue(next(c for c in body['columns']
                                 if c['name'] == 'address')['redacted'])
            # And the reviewed columns still work, or this is just a broken page.
            self.assertEqual(row['first_name'], 'Anita')

    def test_a_model_nobody_has_reviewed_is_not_browsable(self):
        """A model added to the product must not publish itself to the console."""
        with temporary_tenant('hard_allow2', 'o@allow2.test', 'Allowlisted Two'):
            client = platform_admin()

            original = datasets.ALLOWED_FIELDS.pop('crm_api.customer')
            try:
                listing = client.get(
                    '/api/superadmin/boutiques/hard_allow2/data/').json()
                self.assertNotIn('crm_api.customer',
                                 [d['key'] for d in listing['datasets']])
                # And naming it directly reaches nothing either.
                self.assertEqual(
                    client.get('/api/superadmin/boutiques/hard_allow2/data/'
                               'crm_api.customer/').status_code, 404)
            finally:
                datasets.ALLOWED_FIELDS['crm_api.customer'] = original

    def test_a_masked_column_cannot_be_searched(self):
        """Otherwise ?q= is an oracle: rows come back filtered by a value the
        console refuses to print, so a hidden field can be confirmed one guess
        at a time without ever being shown."""
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
        """The denylist is kept underneath the allowlist, so a careless addition
        to ALLOWED_FIELDS cannot publish a credential."""
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
        """Keeps the review record honest. A field renamed or dropped in the
        product leaves a name here that reviews nothing, and the allowlist
        slowly stops describing the schema it is supposed to govern."""
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
    """Sign-in, sign-out and failure are recorded.

    Measured defect: `console.login` and `console.login_failed` were both in
    AuditLog.ACTIONS from the beginning and neither was written by any code
    anywhere. The trail advertised sign-in history it did not keep -- so a
    reviewer saw suspensions and password resets with no record of who had been
    in the console, and nothing indicated the gap.
    """

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
        # Nobody authenticated, so nobody is the actor. The attempted name is
        # the target -- putting it in `actor` would attribute the attempt to
        # whoever owns that account.
        self.assertEqual(entry.actor, '')
        self.assertEqual(entry.target, 'fail@admin.test')

    def test_a_failed_sign_in_for_an_unknown_account_looks_the_same(self):
        """The response deliberately refuses to say whether an account exists.
        An audit trail that says so instead is a directory by another route."""
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
    """Not a defect found -- a protection verified and pinned.

    The console login is the single most valuable password on the deployment.
    LoginThrottle already guards it and shares its scope with the boutique login
    so an attacker cannot draw two allowances by alternating doors. Measured:
    refused at the 21st wrong password of a 20/hour budget. This test exists so
    that stays true.

    ponytail: DRF throttling counts in LocMemCache, so the real ceiling is
    WEB_CONCURRENCY x the rate -- 40/hour across two workers. That is a speed
    bump against online guessing, not a lockout, and making it exact needs a
    shared cache. Recorded in the production notes rather than fixed here.
    """

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
        """Alternating between the console and the boutique login must not buy
        an attacker a second allowance from the same address."""
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
