"""/auth/login/ and /auth/me/ must describe a user identically.

They have disagreed before (see the core/roles.py docstring), and now that the
frontend builds its navigation from "modules" a disagreement is visible: the
menu would change shape on the first page refresh after signing in.
"""

from django.contrib.auth.models import User
from django.db import connection
from django_tenants.test.cases import TenantTestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from crm_api.models import BoutiqueSettings, Tailor
from tenants.middleware import clear_tenant_cache
from tenants.models import BoutiqueTenant

OWNER_EMAIL = 'owner@modules.test'
OWNER_PASSWORD = 'owner-password-77'
TAILOR_EMAIL = 'stitcher@modules.test'
TAILOR_PASSWORD = 'tailor-password-77'


class AuthModulePayloadTests(TenantTestCase):

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = OWNER_EMAIL
        tenant.name = 'Module Atelier'
        return tenant

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        self.addCleanup(clear_tenant_cache)

        self.owner = User.objects.create_user(
            username=OWNER_EMAIL, email=OWNER_EMAIL, password=OWNER_PASSWORD)
        self.tailor_user = User.objects.create_user(
            username=TAILOR_EMAIL, email=TAILOR_EMAIL, password=TAILOR_PASSWORD)
        Tailor.objects.create(name='Anya', specialty='Lehenga', role='Tailor',
                              status='Available', user=self.tailor_user)
        self.settings_row = BoutiqueSettings.objects.get_or_create(id=1)[0]

    # -- helpers ---------------------------------------------------------

    def login(self, username, password):
        response = APIClient().post(
            '/api/auth/login/',
            {'username': username, 'password': password}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def me(self, token):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Token ' + token,
                           HTTP_X_TENANT_ID=self.tenant.schema_name)
        response = client.get('/api/auth/me/')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def set_enabled_modules(self, enabled_modules):
        connection.set_schema_to_public()
        BoutiqueTenant.objects.filter(pk=self.tenant.pk).update(
            enabled_modules=enabled_modules)
        clear_tenant_cache()
        connection.set_tenant(self.tenant)

    def set_role_modules(self, role_modules):
        connection.set_tenant(self.tenant)
        BoutiqueSettings.objects.filter(pk=self.settings_row.pk).update(
            role_modules=role_modules)

    # -- tests -----------------------------------------------------------

    def test_login_and_me_return_the_same_user_dict(self):
        for username, password in ((OWNER_EMAIL, OWNER_PASSWORD),
                                   (TAILOR_EMAIL, TAILOR_PASSWORD)):
            with self.subTest(user=username):
                body = self.login(username, password)
                me = self.me(body['token'])
                # tenant_id is the only key /auth/me/ may add, and login
                # carries it as a sibling of the user object.
                me_user = {k: v for k, v in me.items() if k != 'tenant_id'}
                self.assertEqual(body['user'], me_user)
                self.assertEqual(me['tenant_id'], body['tenant_id'])
                self.assertIn('modules', me_user)
                self.assertIn('module_groups', me_user)

    def test_an_owner_sees_more_modules_than_a_tailor(self):
        owner = set(self.login(OWNER_EMAIL, OWNER_PASSWORD)['user']['modules'])
        tailor = set(self.login(TAILOR_EMAIL, TAILOR_PASSWORD)['user']['modules'])
        self.assertTrue(tailor < owner,
                        f'tailor {sorted(tailor)} is not a strict subset of '
                        f'owner {sorted(owner)}')

    def test_switching_a_module_off_for_the_boutique_takes_it_from_the_owner(self):
        # Entitlement outranks the role map: the owner distributes access, but
        # cannot hand out what the platform has not sold the boutique.
        before = self.login(OWNER_EMAIL, OWNER_PASSWORD)['user']
        self.assertIn('tailors', before['modules'])

        self.set_enabled_modules({'tailors': False})

        after = self.login(OWNER_EMAIL, OWNER_PASSWORD)['user']
        self.assertNotIn('tailors', after['modules'])
        self.assertNotIn('tailors',
                         [k for keys in after['module_groups'].values() for k in keys])
        self.assertNotIn('tailors', self.me(self.token_for(self.owner))['modules'])

    def test_the_owner_can_take_a_module_off_a_role_but_keeps_it(self):
        tailor_before = self.login(TAILOR_EMAIL, TAILOR_PASSWORD)['user']['modules']
        self.assertTrue(tailor_before, 'a Tailor with no modules proves nothing')
        target = tailor_before[0]

        self.set_role_modules({'Tailor': {target: False}})

        self.assertNotIn(target,
                         self.login(TAILOR_EMAIL, TAILOR_PASSWORD)['user']['modules'])
        self.assertIn(target,
                      self.login(OWNER_EMAIL, OWNER_PASSWORD)['user']['modules'])

    def test_module_groups_only_contains_modules_that_are_in_modules(self):
        for username, password in ((OWNER_EMAIL, OWNER_PASSWORD),
                                   (TAILOR_EMAIL, TAILOR_PASSWORD)):
            with self.subTest(user=username):
                payload = self.login(username, password)['user']
                grouped = [k for keys in payload['module_groups'].values()
                           for k in keys]
                self.assertEqual(sorted(grouped), sorted(set(grouped)),
                                 'a module appears in two groups')
                self.assertTrue(set(grouped) <= set(payload['modules']),
                                f'{sorted(set(grouped) - set(payload["modules"]))} '
                                'is grouped but not granted')

    def test_login_survives_a_boutique_with_no_settings_row(self):
        # A tenant provisioned before seed_tenant_defaults ran has no
        # BoutiqueSettings. Login is the one endpoint that must never 500.
        BoutiqueSettings.objects.all().delete()
        payload = self.login(OWNER_EMAIL, OWNER_PASSWORD)['user']
        self.assertTrue(payload['modules'])

    def token_for(self, user):
        connection.set_tenant(self.tenant)
        return Token.objects.get_or_create(user=user)[0].key
