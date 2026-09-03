from contextlib import contextmanager
from pathlib import Path

from django.contrib.auth.models import User
from django.db import connection
from django.test import Client, TransactionTestCase
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.catalog.models import GarmentJob, GarmentTemplate
from apps.catalog.services import sync_global_templates
from apps.design_studio.models import Designer, DesignAssignment
from crm_api.models import Customer, Order
from tenants.middleware import clear_platform_cache, clear_tenant_cache
from tenants.models import BoutiqueTenant, DemoRequest, Domain
from tenants.views import HONEYPOT_FIELD


@contextmanager
def temporary_tenant(schema_name, owner_email, name):
    connection.set_schema_to_public()
    tenant = BoutiqueTenant(schema_name=schema_name, owner_email=owner_email, name=name)
    tenant.save()
    Domain.objects.create(domain=f'{schema_name}.localhost', tenant=tenant, is_primary=True)
    try:
        yield tenant
    finally:
        connection.set_schema_to_public()
        tenant.delete(force_drop=True)


def get_customers(token_schema, tenant_header):
    from django.contrib.auth.models import User
    from rest_framework.authtoken.models import Token
    with schema_context(token_schema):
        user, _ = User.objects.get_or_create(username=f'probe@{token_schema}')
        token, _ = Token.objects.get_or_create(user=user)
        key = token.key
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION='Token ' + key,
                       HTTP_X_TENANT_ID=tenant_header)
    return client.get('/api/customers/')


class TenantIsolationTests(TransactionTestCase):

    def _get_customers(self, token_schema, tenant_header):
        return get_customers(token_schema, tenant_header)

    def _names(self, schema):
        response = self._get_customers(schema, schema)
        self.assertEqual(response.status_code, 200)
        return sorted(c['first_name'] for c in response.json())

    def test_interleaved_requests_do_not_leak_customers(self):
        with temporary_tenant('iso_test_a', 'a@isolation.test', 'Atelier A'), \
                temporary_tenant('iso_test_b', 'b@isolation.test', 'Atelier B'):
            with schema_context('iso_test_a'):
                Customer.objects.create(first_name='Ada', last_name='A', mobile_number='9000000001')
                Customer.objects.create(first_name='Bea', last_name='A', mobile_number='9000000002')
            with schema_context('iso_test_b'):
                Customer.objects.create(first_name='Cal', last_name='B', mobile_number='9000000003')

            for _ in range(3):
                self.assertEqual(self._names('iso_test_a'), ['Ada', 'Bea'])
                self.assertEqual(self._names('iso_test_b'), ['Cal'])

    def test_unknown_tenant_header_does_not_inherit_previous_tenant(self):
        with temporary_tenant('iso_test_c', 'c@isolation.test', 'Atelier C'):
            with schema_context('iso_test_c'):
                Customer.objects.create(first_name='Dee', last_name='C', mobile_number='9000000004')

            self.assertEqual(self._names('iso_test_c'), ['Dee'])
            response = self._get_customers('iso_test_c', 'does_not_exist')
            self.assertEqual(response.status_code, 400)
            self.assertIn('Unknown tenant', response.json()['error'])

            self.assertEqual(self._names('iso_test_c'), ['Dee'])


class SuspensionTests(TransactionTestCase):

    def test_api_is_refused_while_suspended_and_restored_after(self):
        with temporary_tenant('susp_test_a', 'a@susp.test', 'Atelier A') as tenant:
            with schema_context('susp_test_a'):
                Customer.objects.create(first_name='Eve', last_name='S',
                                        mobile_number='9000000005')

            self.assertEqual(
                get_customers('susp_test_a', 'susp_test_a').status_code, 200)

            BoutiqueTenant.objects.filter(pk=tenant.pk).update(is_active=False)
            clear_tenant_cache()  # else the middleware serves its cached copy

            response = get_customers('susp_test_a', 'susp_test_a')
            self.assertEqual(response.status_code, 403)
            self.assertIn('suspended', response.json()['error'])

            BoutiqueTenant.objects.filter(pk=tenant.pk).update(is_active=True)
            clear_tenant_cache()
            self.assertEqual(
                get_customers('susp_test_a', 'susp_test_a').status_code, 200)

    def test_login_is_refused_while_suspended(self):
        from django.contrib.auth.models import User

        with temporary_tenant('susp_test_b', 'owner@susp.test', 'Atelier B') as tenant:
            with schema_context('susp_test_b'):
                User.objects.create_user(username='owner@susp.test',
                                         email='owner@susp.test',
                                         password='correct-horse-battery')

            credentials = {'username': 'owner@susp.test',
                           'password': 'correct-horse-battery'}
            ok = APIClient().post('/api/auth/login/', credentials, format='json')
            self.assertEqual(ok.status_code, 200)

            BoutiqueTenant.objects.filter(pk=tenant.pk).update(is_active=False)
            clear_tenant_cache()

            refused = APIClient().post('/api/auth/login/', credentials, format='json')
            self.assertEqual(refused.status_code, 403)
            self.assertIn('suspended', refused.json()['error'])
            self.assertNotIn('token', refused.json())


class DemoRequestIntakeTests(TransactionTestCase):

    URL = '/demo-request/'

    VALID = {
        'name': 'Aarti Rao',
        'boutique': 'Rao Couture',
        'email': 'aarti@raocouture.test',
        'phone': '+91 90000 00001',
        'makes': 'Bridal blouses and lehengas',
        'orders_per_month': '60',
        'people': '8',
        'problem': 'Orders live in a register and a WhatsApp thread.',
    }

    def setUp(self):
        connection.set_schema_to_public()
        DemoRequest.objects.all().delete()

    def test_lands_in_public_schema_even_with_a_tenant_header(self):
        with temporary_tenant('demo_test_a', 'a@demo.test', 'Atelier A') as tenant:
            response = Client().post(
                self.URL, self.VALID, HTTP_X_TENANT_ID=tenant.schema_name
            )
            self.assertEqual(response.status_code, 201)
            self.assertIs(response.json()['ok'], True)

            with schema_context('public'):
                lead = DemoRequest.objects.get(email=self.VALID['email'])
                self.assertEqual(lead.boutique, 'Rao Couture')
                self.assertEqual(lead.status, 'NEW')

    def test_unknown_tenant_header_is_rejected_before_the_view(self):
        response = Client().post(self.URL, self.VALID, HTTP_X_TENANT_ID='no_such_tenant')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(DemoRequest.objects.count(), 0)

    def test_honeypot_is_accepted_but_discarded(self):
        payload = dict(self.VALID, note_ref='http://spam.example')
        with self.assertLogs('tenants.views', level='WARNING') as logged:
            response = Client().post(self.URL, payload)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(DemoRequest.objects.count(), 0)
        self.assertIn('honeypot', logged.output[0])
        self.assertIn(self.VALID['email'], logged.output[0])

    def test_form_page_uses_the_same_honeypot_field_name(self):
        page = (Path(__file__).resolve().parent.parent
                / 'frontend' / 'site' / 'pages' / 'demo.html')
        self.assertIn(f'name="{HONEYPOT_FIELD}"', page.read_text())

    def test_honeypot_field_name_avoids_browser_autofill_tokens(self):
        for token in ('company', 'organization', 'url', 'email', 'name', 'phone'):
            self.assertNotIn(token, HONEYPOT_FIELD)

    def test_malformed_forwarded_header_does_not_500(self):
        for bad in ('notanip', '203.0.113.9:54321', 'a:b:c', '<script>', ''):
            with self.subTest(forwarded=bad):
                response = Client().post(
                    self.URL, dict(self.VALID, email=f'x{abs(hash(bad))}@demo.test'),
                    HTTP_X_FORWARDED_FOR=bad,
                )
                self.assertEqual(response.status_code, 201)

    def test_junk_forwarded_header_is_not_a_way_around_the_rate_limit(self):
        client = Client()
        for i in range(6):
            response = client.post(
                self.URL, dict(self.VALID, email=f'junk{i}@demo.test'),
                HTTP_X_FORWARDED_FOR='not-an-address',
            )
        self.assertEqual(response.status_code, 429)

    def test_textarea_newlines_do_not_eat_the_length_budget(self):
        text = ('x' * 99 + '\r\n') * 20  # 2020 on the wire, 2000 once normalised
        response = Client().post(self.URL, dict(self.VALID, problem=text))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(DemoRequest.objects.get().problem.count('\r'), 0)

    def test_genuinely_overlong_text_is_still_rejected(self):
        response = Client().post(self.URL, dict(self.VALID, problem='x' * 2001))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(DemoRequest.objects.count(), 0)

    def test_rate_limited_per_ip(self):
        client = Client()
        for i in range(5):
            response = client.post(
                self.URL, dict(self.VALID, email=f'lead{i}@demo.test'),
                HTTP_X_FORWARDED_FOR='203.0.113.9',
            )
            self.assertEqual(response.status_code, 201, f'submission {i} rejected')

        blocked = client.post(
            self.URL, dict(self.VALID, email='lead5@demo.test'),
            HTTP_X_FORWARDED_FOR='203.0.113.9',
        )
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(DemoRequest.objects.count(), 5)

        other = client.post(
            self.URL, dict(self.VALID, email='other@demo.test'),
            HTTP_X_FORWARDED_FOR='198.51.100.4',
        )
        self.assertEqual(other.status_code, 201)

    def test_spoofed_forwarded_chain_does_not_grant_a_fresh_quota(self):
        client = Client()
        for i in range(5):
            client.post(self.URL, dict(self.VALID, email=f'chain{i}@demo.test'),
                        HTTP_X_FORWARDED_FOR='203.0.113.77')
        blocked = client.post(
            self.URL, dict(self.VALID, email='chain5@demo.test'),
            HTTP_X_FORWARDED_FOR='9.9.9.9, 8.8.8.8, 203.0.113.77',
        )
        self.assertEqual(blocked.status_code, 429)

    def test_validation_rejects_a_bad_email_and_stores_nothing(self):
        response = Client().post(self.URL, dict(self.VALID, email='not-an-email'))
        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.json()['errors'])
        self.assertEqual(DemoRequest.objects.count(), 0)

    def test_missing_required_fields_are_reported_per_field(self):
        response = Client().post(self.URL, {'name': 'Only a name'})
        self.assertEqual(response.status_code, 400)
        errors = response.json()['errors']
        self.assertEqual(set(errors), {'boutique', 'email', 'phone'})

    def test_get_is_not_allowed(self):
        self.assertEqual(Client().get(self.URL).status_code, 405)

    def test_overlong_field_is_rejected_rather_than_truncated(self):
        response = Client().post(self.URL, dict(self.VALID, problem='x' * 2001))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(DemoRequest.objects.count(), 0)


class SignupIdentityTests(TransactionTestCase):

    def _signup(self, email, **extra):
        payload = {
            'first_name': 'Qa', 'last_name': 'Probe',
            'email_address': email, 'mobile_number': '9600000000',
            'password': 'SignupProbe2026!',
        }
        payload.update(extra)
        return APIClient().post('/api/auth/signup/', payload, format='json')

    def _drop(self, email):
        connection.set_schema_to_public()
        for tenant in BoutiqueTenant.objects.filter(owner_email=email.lower()):
            tenant.delete(force_drop=True)

    def test_signup_reports_the_owner_role(self):
        try:
            response = self._signup('role.probe@ownerflow.test')
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(response.data['user']['role'], 'Owner')
        finally:
            self._drop('role.probe@ownerflow.test')

    def test_the_email_is_stored_lowercase_so_case_cannot_fork_a_boutique(self):
        try:
            first = self._signup('Case.Probe@Ownerflow.test')
            self.assertEqual(first.status_code, 201, first.data)

            second = self._signup('case.probe@ownerflow.test')
            self.assertEqual(second.status_code, 400)

            connection.set_schema_to_public()
            self.assertEqual(
                BoutiqueTenant.objects.filter(
                    owner_email__iexact='case.probe@ownerflow.test').count(), 1)
        finally:
            self._drop('case.probe@ownerflow.test')

    def test_punctuation_in_an_address_cannot_collide_two_boutiques(self):
        try:
            first = self._signup('a.b@collide.test')
            second = self._signup('a-b@collide.test')

            self.assertEqual(first.status_code, 201, first.data)
            self.assertEqual(second.status_code, 201, second.data)
            self.assertNotEqual(first.data['tenant_id'], second.data['tenant_id'])
        finally:
            self._drop('a.b@collide.test')
            self._drop('a-b@collide.test')

    def test_a_long_address_still_fits_a_postgres_identifier(self):

        long_email = ('x' * 60) + '@averylongdomainname.example.test'
        try:
            response = self._signup(long_email)
            self.assertEqual(response.status_code, 201, response.data)
            self.assertLessEqual(len(response.data['tenant_id']), 63)
        finally:
            self._drop(long_email)


class SignupBoutiqueIdentityTests(TransactionTestCase):

    def _drop(self, email):
        connection.set_schema_to_public()
        for tenant in BoutiqueTenant.objects.filter(owner_email=email.lower()):
            tenant.delete(force_drop=True)

    def test_the_boutiques_own_details_land_on_its_settings(self):
        email = 'identity.probe@ownerflow.test'
        try:
            response = APIClient().post('/api/auth/signup/', {
                'first_name': 'Aditi', 'last_name': 'Rao',
                'email_address': email, 'mobile_number': '9600004444',
                'password': 'SignupProbe2026!',
                'business_name': "Aditi's Atelier",
                'business_address': '4 Nungambakkam High Road, Chennai 600034',
            }, format='json')
            self.assertEqual(response.status_code, 201, response.data)

            from crm_api.models import BoutiqueSettings
            with schema_context(response.data['tenant_id']):
                settings_row = BoutiqueSettings.objects.get(id=1)
                self.assertEqual(settings_row.name, "Aditi's Atelier")
                self.assertEqual(settings_row.email, email)
                self.assertEqual(settings_row.phone, '9600004444')
                self.assertIn('Nungambakkam', settings_row.address)
        finally:
            self._drop(email)

    def test_a_boutique_that_names_nothing_still_gets_sensible_defaults(self):
        email = 'default.probe@ownerflow.test'
        try:
            response = APIClient().post('/api/auth/signup/', {
                'first_name': 'Qa', 'last_name': 'Probe',
                'email_address': email, 'password': 'SignupProbe2026!',
            }, format='json')
            self.assertEqual(response.status_code, 201, response.data)

            from crm_api.models import BoutiqueSettings
            with schema_context(response.data['tenant_id']):
                self.assertEqual(BoutiqueSettings.objects.get(id=1).name, "Qa's Boutique")
        finally:
            self._drop(email)


def tenant_client(schema_name):
    from django.contrib.auth.models import User
    from rest_framework.authtoken.models import Token
    with schema_context(schema_name):
        user, _ = User.objects.get_or_create(username=f'probe@{schema_name}')
        token, _ = Token.objects.get_or_create(user=user)
        key = token.key
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION='Token ' + key, HTTP_X_TENANT_ID=schema_name)
    return client


def set_modules(tenant, enabled_modules):
    connection.set_schema_to_public()
    BoutiqueTenant.objects.filter(pk=tenant.pk).update(enabled_modules=enabled_modules)
    clear_tenant_cache()


class ModuleGateTests(TransactionTestCase):

    def test_a_disabled_module_is_refused_and_the_message_names_it(self):
        with temporary_tenant('mod_test_a', 'a@mod.test', 'Atelier A') as tenant:
            client = tenant_client('mod_test_a')
            self.assertEqual(client.get('/api/fabrics/').status_code, 200)

            set_modules(tenant, {'fabrics': False})

            response = client.get('/api/fabrics/')
            self.assertEqual(response.status_code, 403)
            body = response.json()
            self.assertIn('Fabrics', body['error'])
            self.assertEqual(body['module'], 'fabrics')
            self.assertNotIn('suspended', body['error'])

    def test_everything_disabled_still_leaves_the_boutique_a_way_in(self):
        from core.modules import MODULES

        with temporary_tenant('mod_test_b', 'owner@mod.test', 'Atelier B') as tenant:
            with schema_context('mod_test_b'):
                from django.contrib.auth.models import User
                User.objects.create_user(username='owner@mod.test',
                                         email='owner@mod.test',
                                         password='correct-horse-battery')

            set_modules(tenant, {key: False for key in MODULES})

            login = APIClient().post('/api/auth/login/',
                                     {'username': 'owner@mod.test',
                                      'password': 'correct-horse-battery'},
                                     format='json')
            self.assertEqual(login.status_code, 200)

            client = tenant_client('mod_test_b')
            self.assertEqual(client.get('/api/dashboard/').status_code, 200)
            self.assertEqual(client.get('/api/boutique-settings/').status_code, 200)
            self.assertEqual(client.get('/api/customers/').status_code, 200)

    def test_disabling_a_parent_prefix_does_not_take_its_child_with_it(self):
        with temporary_tenant('mod_test_c', 'c@mod.test', 'Atelier C') as tenant:
            client = tenant_client('mod_test_c')

            set_modules(tenant, {'inventory': False})
            self.assertEqual(client.get('/api/inventory/items/').status_code, 403)
            self.assertEqual(client.get('/api/inventory/catalog/items/').status_code, 200)

            set_modules(tenant, {'inventory_catalog': False})
            self.assertEqual(client.get('/api/inventory/items/').status_code, 200)
            catalog = client.get('/api/inventory/catalog/items/')
            self.assertEqual(catalog.status_code, 403)
            self.assertEqual(catalog.json()['module'], 'inventory_catalog')

    def test_a_module_nobody_has_an_opinion_about_is_on(self):
        with temporary_tenant('mod_test_d', 'd@mod.test', 'Atelier D') as tenant:
            client = tenant_client('mod_test_d')

            connection.set_schema_to_public()
            self.assertEqual(
                BoutiqueTenant.objects.get(pk=tenant.pk).enabled_modules, {})
            self.assertEqual(client.get('/api/fabrics/').status_code, 200)

            set_modules(tenant, {'inventory': False})
            self.assertEqual(client.get('/api/fabrics/').status_code, 200)


class MaintenanceModeTests(TransactionTestCase):

    def _set_maintenance(self, **value):
        from superadmin.models import PlatformSetting
        connection.set_schema_to_public()
        PlatformSetting.objects.update_or_create(
            key='maintenance_mode', defaults={'value': value})
        clear_platform_cache()
        self.addCleanup(clear_platform_cache)

    def test_a_boutique_is_refused_but_the_console_is_not(self):
        with temporary_tenant('maint_test_a', 'a@maint.test', 'Atelier A'):
            client = tenant_client('maint_test_a')
            self.assertEqual(client.get('/api/customers/').status_code, 200)

            self._set_maintenance(enabled=True, message='Back at 03:00 UTC.')

            response = client.get('/api/customers/')
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()['error'], 'Back at 03:00 UTC.')

            console = APIClient().post('/api/superadmin/auth/login/',
                                       {'username': 'nobody', 'password': 'nobody'},
                                       format='json')
            self.assertNotEqual(console.status_code, 503)

            login = APIClient().post('/api/auth/login/',
                                     {'username': 'nobody', 'password': 'nobody'},
                                     format='json')
            self.assertNotEqual(login.status_code, 503)

            self._set_maintenance(enabled=False)
            self.assertEqual(client.get('/api/customers/').status_code, 200)


class SignupSeedsNothingInventedTests(TransactionTestCase):

    def _signup(self, email):
        return APIClient().post('/api/auth/signup/', {
            'first_name': 'Nita', 'last_name': 'Rao',
            'email_address': email, 'password': 'a-real-password-42',
            'business_name': "Nita's Atelier",
        }, format='json')

    def test_a_new_boutique_has_no_invented_staff_fabrics_or_designs(self):
        from crm_api.models import BoutiqueFabric, Tailor
        from apps.design_studio.models import DesignAsset

        response = self._signup('nita.seed@ownerflow.test')
        self.assertEqual(response.status_code, 201, response.data)
        schema = response.data['tenant_id']

        with schema_context(schema):
            self.assertEqual(Tailor.objects.count(), 0,
                             list(Tailor.objects.values_list('name', flat=True)))
            self.assertEqual(BoutiqueFabric.objects.count(), 0,
                             list(BoutiqueFabric.objects.values_list('name', flat=True)))
            self.assertFalse(
                DesignAsset.objects.filter(
                    source=DesignAsset.SOURCE_CATALOGUE).exists(),
                'the demo catalogue was seeded into a real boutique')

    def test_the_seed_helper_still_populates_when_asked(self):
        from crm_api.models import BoutiqueFabric, Tailor
        from crm_api.utils import seed_tenant_defaults

        response = self._signup('nita.demo@ownerflow.test')
        schema = response.data['tenant_id']
        with schema_context(schema):
            seed_tenant_defaults()
            self.assertGreater(Tailor.objects.count(), 0)
            self.assertGreater(BoutiqueFabric.objects.count(), 0)


class MultiBoutiqueLoginTests(TransactionTestCase):

    def _signup(self, email, name):
        return APIClient().post('/api/auth/signup/', {
            'first_name': name, 'last_name': 'Owner',
            'email_address': email, 'password': 'owner-password-77',
            'business_name': f"{name}'s Atelier",
        }, format='json')

    def setUp(self):
        super().setUp()
        from crm_api.models import Tailor
        from django.contrib.auth.models import User

        self.schema_a = self._signup('a.owner@twoshops.test', 'Asha').data['tenant_id']
        self.schema_b = self._signup('b.owner@twoshops.test', 'Bina').data['tenant_id']

        self.shared_email = 'freelance.tailor@twoshops.test'
        for schema, password in ((self.schema_a, 'password-at-asha-1'),
                                 (self.schema_b, 'password-at-bina-2')):
            with schema_context(schema):
                user = User.objects.create_user(
                    username=self.shared_email, email=self.shared_email,
                    password=password, first_name='Ravi')
                Tailor.objects.create(name='Ravi', specialty='Blouses',
                                      role='Tailor', status='Available', user=user)

    def _login(self, password):
        from django.core.cache import cache
        cache.clear()   # LoginThrottle counts failures per address
        return APIClient().post('/api/auth/login/',
                                {'username': self.shared_email, 'password': password},
                                format='json')

    def test_each_boutiques_password_signs_in_to_that_boutique(self):
        first = self._login('password-at-asha-1')
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(first.data['tenant_id'], self.schema_a)

        second = self._login('password-at-bina-2')
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(second.data['tenant_id'], self.schema_b)

    def test_a_wrong_password_is_still_refused_after_trying_every_boutique(self):
        response = self._login('not-either-of-them')
        self.assertEqual(response.status_code, 400, response.data)

    def test_a_suspended_boutique_does_not_block_the_other(self):
        with schema_context('public'):
            tenant_a = BoutiqueTenant.objects.get(schema_name=self.schema_a)
            tenant_a.is_active = False
            tenant_a.save(update_fields=['is_active'])
        clear_tenant_cache()
        try:
            response = self._login('password-at-bina-2')
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data['tenant_id'], self.schema_b)
            refused = self._login('password-at-asha-1')
            self.assertEqual(refused.status_code, 403, refused.data)
        finally:
            with schema_context('public'):
                tenant_a.is_active = True
                tenant_a.save(update_fields=['is_active'])
            clear_tenant_cache()


class DesignAssignmentIsolationTests(TransactionTestCase):

    def _seed(self, schema, designer_email, order_id, designer_name):

        with schema_context(schema):
            sync_global_templates()
            customer = Customer.objects.create(
                first_name="Client", last_name=schema, mobile_number="9600003333")
            order = Order.objects.create(order_id=order_id, customer=customer)
            job = GarmentJob.objects.create(
                order=order, template=GarmentTemplate.objects.filter(key='lehenga').first(),
                sequence=0)
            user = User.objects.create_user(
                username=designer_email, email=designer_email, password="pass12345")
            designer = Designer.objects.create(
                name=designer_name, email=designer_email, user=user)
            DesignAssignment.objects.create(garment_job=job, designer=designer)
            token, _ = Token.objects.get_or_create(user=user)
            return token.key

    def _list_assignments(self, token_key, tenant_header):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Token ' + token_key,
                           HTTP_X_TENANT_ID=tenant_header)
        return client.get('/api/design-studio/assignments/')

    def test_a_designer_cannot_read_another_boutiques_assignments(self):
        with temporary_tenant('asn_test_a', 'a@asn.test', 'Atelier A'), \
                temporary_tenant('asn_test_b', 'b@asn.test', 'Atelier B'):
            key_a = self._seed('asn_test_a', 'meera@asn-a.test', 'T2B-A-0001', 'Meera')
            self._seed('asn_test_b', 'kavya@asn-b.test', 'T2B-B-0001', 'Kavya')

            response = self._list_assignments(key_a, 'asn_test_b')
            rows = response.data if response.status_code == 200 else []
            rows = rows['results'] if isinstance(rows, dict) else rows
            self.assertNotIn('T2B-B-0001', str(rows))
            self.assertNotIn('Kavya', str(rows))

    def test_each_boutique_sees_exactly_its_own_row(self):
        with temporary_tenant('asn_test_c', 'c@asn.test', 'Atelier C'), \
                temporary_tenant('asn_test_d', 'd@asn.test', 'Atelier D'):
            key_c = self._seed('asn_test_c', 'meera@asn-c.test', 'T2B-C-0001', 'Meera')
            key_d = self._seed('asn_test_d', 'kavya@asn-d.test', 'T2B-D-0001', 'Kavya')

            for _ in range(2):
                rows_c = self._list_assignments(key_c, 'asn_test_c').data
                rows_c = rows_c['results'] if isinstance(rows_c, dict) else rows_c
                self.assertEqual([r['order_ref'] for r in rows_c], ['T2B-C-0001'])

                rows_d = self._list_assignments(key_d, 'asn_test_d').data
                rows_d = rows_d['results'] if isinstance(rows_d, dict) else rows_d
                self.assertEqual([r['order_ref'] for r in rows_d], ['T2B-D-0001'])


class TenantCacheInvalidationTests(TransactionTestCase):

    def test_saving_a_tenant_clears_the_cache(self):
        from tenants.middleware import _get_tenant_by_schema, _tenant_cache
        with temporary_tenant('cache_test_a', 'first@cache.test', 'Atelier A') as tenant:
            cached = _get_tenant_by_schema(BoutiqueTenant, 'cache_test_a')
            self.assertEqual(cached.owner_email, 'first@cache.test')
            self.assertIn('cache_test_a', _tenant_cache)

            tenant.owner_email = 'second@cache.test'
            tenant.save()

            self.assertNotIn('cache_test_a', _tenant_cache)
            refreshed = _get_tenant_by_schema(BoutiqueTenant, 'cache_test_a')
            self.assertEqual(refreshed.owner_email, 'second@cache.test')

    def test_deleting_a_tenant_clears_the_cache(self):
        from tenants.middleware import _get_tenant_by_schema, _tenant_cache
        with temporary_tenant('cache_test_b', 'gone@cache.test', 'Atelier B'):
            _get_tenant_by_schema(BoutiqueTenant, 'cache_test_b')
            self.assertIn('cache_test_b', _tenant_cache)
        self.assertNotIn('cache_test_b', _tenant_cache)
        self.assertIsNone(_get_tenant_by_schema(BoutiqueTenant, 'cache_test_b'))


class PricingIsolationTests(TransactionTestCase):

    def _priced_order(self, schema, order_id, base):
        from decimal import Decimal
        from crm_api.models import BoutiqueSettings
        with schema_context(schema):
            BoutiqueSettings.objects.get_or_create(id=1)
            customer = Customer.objects.create(
                first_name='Client', last_name=schema, mobile_number='9600004444')
            total = (Decimal(base) * Decimal('1.05')).quantize(Decimal('0.01'))
            Order.objects.create(
                order_id=order_id, customer=customer,
                base_price=Decimal(base), taxes=total - Decimal(base),
                total_amount=total, amount_paid=total, payment_status='Paid')
            return total

    def test_each_boutiques_revenue_is_its_own(self):
        with temporary_tenant('price_test_a', 'a@price.test', 'Atelier A'), \
                temporary_tenant('price_test_b', 'b@price.test', 'Atelier B'):
            total_a = self._priced_order('price_test_a', 'T2B-PA-1', '10000')
            total_b = self._priced_order('price_test_b', 'T2B-PB-1', '70000')
            self.assertNotEqual(total_a, total_b)

            for schema, expected in (('price_test_a', total_a),
                                     ('price_test_b', total_b)):
                response = tenant_client(schema).get('/api/dashboard/')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    str(response.data['stats']['revenue']), str(float(expected)),
                    f'{schema} revenue must be exactly its own order')


class QCQueueIsolationTests(TransactionTestCase):

    def _boutique_at_qc(self, schema, order_id, qc_email):

        from crm_api.models import BoutiqueSettings, Measurement, Tailor
        from domains.orders.services import OrderService
        with schema_context(schema):
            BoutiqueSettings.objects.get_or_create(id=1)
            qc_user = User.objects.create_user(
                username=qc_email, email=qc_email, password='qcpass12345')
            Tailor.objects.create(name=f'Inspector {schema}', specialty='Bridal',
                                  role='QC Master', status='Available', user=qc_user)
            tailor = Tailor.objects.create(name='Stitcher', specialty='Bridal',
                                           role='Tailor', status='Available')
            customer = Customer.objects.create(
                first_name='Client', last_name=schema, mobile_number='9600005555')
            Measurement.objects.create(customer=customer, bust=36, waist=30, hips=38)
            owner = User.objects.create_user(
                username=f'owner@{schema}', email=f'owner@{schema}',
                password='ownerpass12345', is_superuser=True)
            order = OrderService.create_order_for_customer(
                customer, {'base_price': 10000, 'tailor_id': tailor.id}, user=owner)

            config = BoutiqueSettings.objects.get(id=1).workflow_config
            keys = [s['key'] for s in config]
            for earlier in keys[:keys.index('master_quality_check')]:
                stage = order.stages.filter(stage_key=earlier).first()
                if stage is None or stage.status in ('COMPLETED', 'SKIPPED'):
                    continue
                optional = next(
                    (s.get('optional') for s in config if s['key'] == earlier), False)
                OrderService.transition_order_stage(
                    order=order, stage_key=earlier,
                    new_status='SKIPPED' if optional else 'COMPLETED', user=owner)
            Order.objects.filter(pk=order.pk).update(order_id=order_id)
            token, _ = Token.objects.get_or_create(user=qc_user)
            return token.key

    def _queue(self, token_key, tenant_header):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Token ' + token_key,
                           HTTP_X_TENANT_ID=tenant_header)
        return client.get('/api/orders/')

    def test_a_qc_master_queue_holds_only_their_own_boutiques_work(self):
        with temporary_tenant('qc_test_a', 'a@qc.test', 'Atelier A'), \
                temporary_tenant('qc_test_b', 'b@qc.test', 'Atelier B'):
            key_a = self._boutique_at_qc('qc_test_a', 'T2B-QA-1', 'qc@qc-a.test')
            key_b = self._boutique_at_qc('qc_test_b', 'T2B-QB-1', 'qc@qc-b.test')

            for _ in range(2):
                rows_a = self._queue(key_a, 'qc_test_a').data
                rows_a = rows_a['results'] if isinstance(rows_a, dict) else rows_a
                self.assertEqual([r['order_id'] for r in rows_a], ['T2B-QA-1'])

                rows_b = self._queue(key_b, 'qc_test_b').data
                rows_b = rows_b['results'] if isinstance(rows_b, dict) else rows_b
                self.assertEqual([r['order_id'] for r in rows_b], ['T2B-QB-1'])

    def test_a_token_from_one_boutique_does_not_open_anothers_queue(self):
        with temporary_tenant('qc_test_c', 'c@qc.test', 'Atelier C'), \
                temporary_tenant('qc_test_d', 'd@qc.test', 'Atelier D'):
            key_c = self._boutique_at_qc('qc_test_c', 'T2B-QC-1', 'qc@qc-c.test')
            self._boutique_at_qc('qc_test_d', 'T2B-QD-1', 'qc@qc-d.test')

            response = self._queue(key_c, 'qc_test_d')
            rows = response.data if response.status_code == 200 else []
            rows = rows['results'] if isinstance(rows, dict) else rows
            self.assertNotIn('T2B-QD-1', str(rows))
