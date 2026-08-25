"""Regression tests for the final security gate.

Two P0s were found here and both were measured before they were fixed, not
reasoned about:

  1. **/admin/ was outside every perimeter.** The console's public-schema pin
     covered `/api/superadmin/` only. `tenants` and `superadmin` are SHARED_APPS,
     so their tables exist only in `public` -- but a tenant search_path is
     `'<tenant>', public`, so they still resolve from inside a boutique, while
     `auth_user` (in BOTH app lists) resolves to the BOUTIQUE's table. Sending
     `X-Tenant-ID: <my own boutique>` to /admin/login/ therefore let a boutique's
     own superuser authenticate and then administer the PLATFORM. Measured: it
     read the full registry, read the platform audit log, and SUSPENDED a
     different boutique. `IsPlatformAdmin` never ran, because /admin/ is not DRF.

  2. **The platform administrator's password could be reset through the
     boutique flow.** `find_tenants_for_account` scans every registry row for a
     matching account; inside a schema that does not exist that scan reads
     `public`, where the platform administrator lives. Measured: a reset request
     for the administrator's address minted a valid token naming the ghost
     schema, and the confirm endpoint accepted it and overwrote the password.

Both are closed at shared boundaries rather than at call sites -- `PUBLIC_ONLY_
PREFIXES` in tenants/middleware.py, and `EXTRA_SET_TENANT_METHOD_PATH` (django-
tenants' own hook into every `set_tenant`) in tenants/schema_guard.py.
"""

from django.contrib.auth.models import User
from django.core import mail, signing
from django.core.cache import cache
from django.db import connection
from django.test import TransactionTestCase
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from crm_api.models import Customer, Order
from superadmin import datasets
from superadmin.models import AuditLog
from superadmin.schemas import MissingSchema
from superadmin.test_users_search import ghost_tenant
from superadmin.tests import temporary_tenant
from tenants.middleware import clear_tenant_cache
from tenants.models import BoutiqueTenant


def console_client(username='gate@admin.test', password='GateAdminPw-2026'):
    connection.set_schema_to_public()
    User.objects.filter(username=username).delete()
    User.objects.create_superuser(username=username, email=username, password=password)
    client = APIClient()
    response = client.post('/api/superadmin/auth/login/',
                           {'username': username, 'password': password}, format='json')
    assert response.status_code == 200, response.content
    client.credentials(HTTP_AUTHORIZATION='Token ' + response.json()['token'])
    return client


class DjangoAdminIsPlatformOnly(TransactionTestCase):
    """P0-1. /admin/ is pinned to the public schema."""

    def setUp(self):
        connection.set_schema_to_public()
        cache.clear()
        clear_tenant_cache()

    def test_a_boutique_superuser_cannot_administer_the_platform(self):
        with temporary_tenant('gt_adm_a', 'a@gt.test', 'Target A'), \
             temporary_tenant('gt_adm_b', 'b@gt.test', 'Target B') as victim:
            clear_tenant_cache()
            with schema_context('gt_adm_a'):
                User.objects.create_superuser(username='rogue@gt.test',
                                              email='rogue@gt.test',
                                              password='RoguePw-2026!')

            client = APIClient()
            client.post('/admin/login/',
                        {'username': 'rogue@gt.test', 'password': 'RoguePw-2026!',
                         'next': '/admin/'},
                        HTTP_X_TENANT_ID='gt_adm_a')

            listing = client.get('/admin/tenants/boutiquetenant/',
                                 HTTP_X_TENANT_ID='gt_adm_a')
            body = listing.content.decode(errors='replace')
            self.assertNotIn('gt_adm_b', body,
                             'a boutique superuser read the platform registry')
            self.assertNotIn('Target B', body)

            # And the action that would take the platform down.
            connection.set_schema_to_public()
            client.post('/admin/tenants/boutiquetenant/',
                        {'action': 'suspend', '_selected_action': [str(victim.pk)]},
                        HTTP_X_TENANT_ID='gt_adm_a')
            connection.set_schema_to_public()
            self.assertTrue(
                BoutiqueTenant.objects.get(pk=victim.pk).is_active,
                'a boutique superuser suspended a different boutique through /admin/')

    def test_the_platform_administrator_can_still_use_the_admin(self):
        """The fix must not lock out the person it is protecting."""
        connection.set_schema_to_public()
        User.objects.filter(username='real@gt.test').delete()
        User.objects.create_superuser(username='real@gt.test', email='real@gt.test',
                                      password='RealAdminPw-2026!')
        client = APIClient()
        signed_in = client.post('/admin/login/',
                                {'username': 'real@gt.test',
                                 'password': 'RealAdminPw-2026!', 'next': '/admin/'})
        self.assertEqual(signed_in.status_code, 302, 'the platform admin was locked out')
        self.assertEqual(client.get('/admin/tenants/boutiquetenant/').status_code, 200)

    def test_the_admin_stays_on_public_even_when_a_tenant_is_named(self):
        with temporary_tenant('gt_pin', 'p@gt.test', 'Pin'):
            clear_tenant_cache()
            APIClient().get('/admin/', HTTP_X_TENANT_ID='gt_pin')
            self.assertEqual(connection.schema_name, 'public')


class PlatformAccountIsUnreachableFromTenantFlows(TransactionTestCase):
    """P0-2. No boutique-scoped flow may resolve the platform administrator."""

    def setUp(self):
        connection.set_schema_to_public()
        cache.clear()
        clear_tenant_cache()
        User.objects.filter(username='platform@gt.test').delete()
        self.admin = User.objects.create_superuser(
            username='platform@gt.test', email='platform@gt.test',
            password='PlatformPw-2026')

    def test_password_reset_cannot_mint_a_token_for_the_platform_account(self):
        with ghost_tenant('gt_ghost_pw', 'o@gp.test', 'Ghost PW'):
            clear_tenant_cache()
            mail.outbox = []
            response = APIClient().post('/api/auth/password-reset/',
                                        {'email': 'platform@gt.test'}, format='json')

            self.assertEqual(len(mail.outbox), 0,
                             'a reset link was minted for the platform administrator')
            self.assertNotEqual(response.status_code, 500)

            connection.set_schema_to_public()
            self.assertTrue(
                User.objects.get(pk=self.admin.pk).check_password('PlatformPw-2026'),
                'the platform administrator password was changed')

    def test_a_reset_payload_naming_a_ghost_schema_is_refused(self):
        """The confirm endpoint takes its schema from request-body text."""
        with temporary_tenant('gt_real_pw', 'r@gp.test', 'Real PW'), \
             ghost_tenant('gt_ghost_pw2', 'o2@gp.test', 'Ghost PW2'):
            clear_tenant_cache()
            from django.contrib.auth.tokens import default_token_generator
            from django.utils.encoding import force_bytes
            from django.utils.http import urlsafe_base64_encode

            connection.set_schema_to_public()
            uid = urlsafe_base64_encode(force_bytes(self.admin.pk))
            token = default_token_generator.make_token(self.admin)
            forged = f'gt_ghost_pw2.{uid}.{token}'

            response = APIClient().post('/api/auth/password-reset/confirm/',
                                        {'token': forged, 'password': 'AttackerPw-4242'},
                                        format='json')
            self.assertNotEqual(response.status_code, 200)
            connection.set_schema_to_public()
            self.assertTrue(
                User.objects.get(pk=self.admin.pk).check_password('PlatformPw-2026'))

    def test_login_refuses_a_ghost_and_leaks_no_database_detail(self):
        with ghost_tenant('gt_ghost_login', 'o@gl.test', 'Ghost Login'):
            clear_tenant_cache()
            response = APIClient().post(
                '/api/auth/login/',
                {'username': 'platform@gt.test', 'password': 'PlatformPw-2026'},
                format='json')
            self.assertNotEqual(response.status_code, 200,
                                'the platform account signed in as a boutique user')
            body = response.content.decode(errors='replace')
            # The raw Postgres error used to be returned verbatim, naming real
            # tables and columns to an unauthenticated caller.
            self.assertNotIn('does not exist', body)
            self.assertNotIn('relation', body)
            self.assertNotIn('LINE 1', body)

    def test_the_public_tracking_page_refuses_a_ghost(self):
        from domains.orders.tracking import SALT
        with ghost_tenant('gt_ghost_track', 'o@gt2.test', 'Ghost Track'):
            clear_tenant_cache()
            token = signing.dumps({'s': 'gt_ghost_track', 'o': 'T2B-260101-0001'},
                                  salt=SALT)
            response = APIClient().get(f'/track/{token}/')
            self.assertEqual(response.status_code, 503)


class TheSchemaGuardIsGlobal(TransactionTestCase):
    """The boundary itself, rather than any one caller of it."""

    def setUp(self):
        connection.set_schema_to_public()
        cache.clear()
        clear_tenant_cache()

    def test_entering_a_missing_schema_raises_wherever_it_is_attempted(self):
        with ghost_tenant('gt_guard', 'g@gt.test', 'Guard'):
            with self.assertRaises(MissingSchema):
                with schema_context('gt_guard'):
                    pass
            # And the connection is left somewhere safe rather than pointed at a
            # schema Postgres would resolve to public.
            self.assertEqual(connection.schema_name, 'public')

    def test_public_and_real_schemas_are_unaffected(self):
        with schema_context('public'):
            self.assertEqual(connection.schema_name, 'public')
        with temporary_tenant('gt_ok', 'ok@gt.test', 'OK'):
            with schema_context('gt_ok'):
                self.assertEqual(connection.schema_name, 'gt_ok')
        self.assertEqual(connection.schema_name, 'public')

    def test_creating_a_boutique_still_works(self):
        """The guard must not break the one flow that legitimately switches
        into a schema that did not exist a moment earlier."""
        with temporary_tenant('gt_create', 'c@gt.test', 'Created') as tenant:
            self.assertTrue(tenant.pk)
            with schema_context('gt_create'):
                Customer.objects.create(first_name='New', last_name='Boutique',
                                        mobile_number='9000000777')
                self.assertEqual(Customer.objects.count(), 1)


class DataBrowserResidualLeaks(TransactionTestCase):
    def setUp(self):
        connection.set_schema_to_public()
        cache.clear()
        clear_tenant_cache()

    def test_a_ghost_boutique_never_renders_platform_accounts(self):
        client = console_client()
        with ghost_tenant('gt_ghost_db', 'o@gd.test', 'Ghost DB'):
            clear_tenant_cache()
            response = client.get(
                '/api/superadmin/boutiques/gt_ghost_db/data/auth.user/')
            self.assertNotEqual(response.status_code, 200)
            self.assertNotIn('gate@admin.test', response.content.decode(errors='replace'),
                             'public-schema accounts were rendered as a boutique\'s staff')

    def test_a_related_row_that_is_not_browsable_is_not_rendered(self):
        """__str__ answers to no allowlist, so it is only shown for models the
        allowlist has actually approved."""
        client = console_client()
        with temporary_tenant('gt_rel', 'r@gd.test', 'Rel'):
            clear_tenant_cache()
            with schema_context('gt_rel'):
                cust = Customer.objects.create(first_name='Ann', last_name='B',
                                               mobile_number='9000000999')
                Order.objects.create(order_id='T2B-260101-0009', customer=cust,
                                     total_amount=100)

            original = datasets.ALLOWED_FIELDS.pop('crm_api.customer')
            try:
                body = client.get('/api/superadmin/boutiques/gt_rel/data/'
                                  'crm_api.order/').content.decode(errors='replace')
            finally:
                datasets.ALLOWED_FIELDS['crm_api.customer'] = original

            self.assertNotIn('9000000999', body,
                             "an unreviewed model's __str__ leaked through a "
                             'relation column')

    def test_an_unreviewed_credential_shaped_field_is_masked(self):
        """The names a denylist would have missed.

        Measured against the denylist this replaced: every one of these passed
        it untouched. Under the allowlist a field is masked unless it has been
        reviewed onto its model's list, whatever it is called.
        """
        class Field:
            def __init__(self, name):
                self.name = name

        unexpected = ('gateway_credential', 'webhook_signing', 'otp_seed',
                      'recovery_code', 'session_key', 'pat', 'shared_salt',
                      'device_fingerprint', 'sso_assertion')
        for name in unexpected:
            self.assertTrue(
                datasets._is_redacted(Field(name), 'crm_api.customer'),
                f'{name!r} would be rendered without ever having been reviewed')

        # And the old denylist is still underneath, so a careless addition to
        # ALLOWED_FIELDS cannot publish an obvious credential.
        for name in ('password', 'api_key', 'auth_token', 'client_secret'):
            self.assertTrue(datasets._is_redacted(Field(name)))


class PrivilegedReadsAreAudited(TransactionTestCase):
    def setUp(self):
        connection.set_schema_to_public()
        cache.clear()
        clear_tenant_cache()
        AuditLog.objects.all().delete()

    def _entries(self):
        connection.set_schema_to_public()
        return list(AuditLog.objects.filter(action='data.view'))

    def test_a_platform_wide_search_is_recorded(self):
        with temporary_tenant('gt_search', 's@gt.test', 'Search'):
            clear_tenant_cache()
            with schema_context('gt_search'):
                Customer.objects.create(first_name='Findme', last_name='X',
                                        mobile_number='9000000321')
            client = console_client()
            connection.set_schema_to_public()
            AuditLog.objects.all().delete()

            client.get('/api/superadmin/search/?q=9000000321')
            entries = self._entries()
            self.assertEqual(len(entries), 1, 'a cross-boutique search left no trail')
            self.assertEqual(entries[0].after['access'], 'search')
            self.assertEqual(entries[0].after['search'], '9000000321')

    def test_a_term_too_short_to_run_is_not_recorded(self):
        client = console_client()
        connection.set_schema_to_public()
        AuditLog.objects.all().delete()
        client.get('/api/superadmin/search/?q=a')
        self.assertEqual(self._entries(), [])

    def test_the_user_directory_is_recorded(self):
        with temporary_tenant('gt_users', 'u@gt.test', 'Users'):
            clear_tenant_cache()
            client = console_client()
            connection.set_schema_to_public()
            AuditLog.objects.all().delete()

            client.get('/api/superadmin/users/')
            entries = self._entries()
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].after['access'], 'user_directory')
            self.assertEqual(entries[0].boutique, '',
                             'a platform-wide sweep should be distinguishable '
                             'from one boutique')

            AuditLog.objects.all().delete()
            client.get('/api/superadmin/users/?boutique=gt_users')
            self.assertEqual(self._entries()[0].boutique, 'gt_users')


class DjangoAdminSuspensionIsAudited(TransactionTestCase):
    """The back door writes to the same trail as the front door."""

    def setUp(self):
        connection.set_schema_to_public()
        cache.clear()
        clear_tenant_cache()
        User.objects.filter(username='adminaudit@gt.test').delete()
        User.objects.create_superuser(username='adminaudit@gt.test',
                                      email='adminaudit@gt.test',
                                      password='AdminAuditPw-2026!')
        AuditLog.objects.all().delete()

    def test_a_bulk_suspension_writes_an_audit_row_per_boutique(self):
        with temporary_tenant('gt_aud_a', 'a@aa.test', 'Aud A') as a, \
             temporary_tenant('gt_aud_b', 'b@aa.test', 'Aud B') as b:
            clear_tenant_cache()
            client = APIClient()
            client.post('/admin/login/', {'username': 'adminaudit@gt.test',
                                          'password': 'AdminAuditPw-2026!',
                                          'next': '/admin/'})
            connection.set_schema_to_public()
            AuditLog.objects.all().delete()

            client.post('/admin/tenants/boutiquetenant/',
                        {'action': 'suspend',
                         '_selected_action': [str(a.pk), str(b.pk)]})

            connection.set_schema_to_public()
            suspensions = AuditLog.objects.filter(action='boutique.suspend')
            self.assertEqual(suspensions.count(), 2,
                             'suspending from the Django admin left no trail')
            self.assertEqual(
                sorted(suspensions.values_list('boutique', flat=True)),
                ['gt_aud_a', 'gt_aud_b'])
            entry = suspensions.first()
            self.assertEqual(entry.actor, 'adminaudit@gt.test')
            self.assertEqual(entry.after, {'is_active': False})
            self.assertIn('Django admin', entry.reason)

            # Leave the boutiques as they were found.
            BoutiqueTenant.objects.filter(pk__in=[a.pk, b.pk]).update(is_active=True)
