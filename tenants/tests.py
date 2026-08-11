from contextlib import contextmanager
from pathlib import Path

from django.db import connection
from django.test import Client, TransactionTestCase
from django_tenants.utils import schema_context
from rest_framework.test import APIClient

from crm_api.models import Customer
from tenants.models import BoutiqueTenant, DemoRequest, Domain
from tenants.views import HONEYPOT_FIELD


@contextmanager
def temporary_tenant(schema_name, owner_email, name):
    """Create a real tenant schema for the duration of a test, then drop it.

    Schema creation is DDL, so these tests use TransactionTestCase and build the
    tenants inside the test body rather than in setUpClass (which would be rolled
    back or flushed away).
    """
    connection.set_schema_to_public()
    tenant = BoutiqueTenant(schema_name=schema_name, owner_email=owner_email, name=name)
    tenant.save()
    Domain.objects.create(domain=f'{schema_name}.localhost', tenant=tenant, is_primary=True)
    try:
        yield tenant
    finally:
        connection.set_schema_to_public()
        tenant.delete(force_drop=True)


class TenantIsolationTests(TransactionTestCase):
    """Guards the schema boundary now that connections are reused between requests.

    With CONN_MAX_AGE > 0 the same DB connection serves consecutive requests, so a
    stale search_path would silently serve one boutique's clients to another.
    """

    def _get_customers(self, token_schema, tenant_header):
        """Call the directory as a user signed in to `token_schema`, addressing
        `tenant_header`.

        The token and the header are separate arguments because they are separate
        concerns -- and because APIClient.credentials() overrides per-request
        headers, so the tenant header has to travel with the credentials.
        """
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

            # Alternate tenants so a leaked search_path shows up as a wrong result.
            for _ in range(3):
                self.assertEqual(self._names('iso_test_a'), ['Ada', 'Bea'])
                self.assertEqual(self._names('iso_test_b'), ['Cal'])

    def test_unknown_tenant_header_does_not_inherit_previous_tenant(self):
        with temporary_tenant('iso_test_c', 'c@isolation.test', 'Atelier C'):
            with schema_context('iso_test_c'):
                Customer.objects.create(first_name='Dee', last_name='C', mobile_number='9000000004')

            # Warm the connection on a real tenant, then ask for one that does not exist.
            self.assertEqual(self._names('iso_test_c'), ['Dee'])
            response = self._get_customers('iso_test_c', 'does_not_exist')
            # A clean rejection, not a 500 and certainly not tenant C's clients.
            self.assertEqual(response.status_code, 400)
            self.assertIn('Unknown tenant', response.json()['error'])

            # The bad request must not poison the connection for the next caller.
            self.assertEqual(self._names('iso_test_c'), ['Dee'])


class DemoRequestIntakeTests(TransactionTestCase):
    """The public demo form posts here with no token, no session and no tenant.

    The branch worth guarding is the schema one: the marketing site is on a
    different origin to the API, so nothing guarantees which tenant the
    middleware resolves, and the lead must land in public either way.
    """

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

            # The row is in public, not in the tenant the header named.
            with schema_context('public'):
                lead = DemoRequest.objects.get(email=self.VALID['email'])
                self.assertEqual(lead.boutique, 'Rao Couture')
                self.assertEqual(lead.status, 'NEW')

    def test_unknown_tenant_header_is_rejected_before_the_view(self):
        # The middleware answers this one, which is why the form must never
        # send an X-Tenant-ID header.
        response = Client().post(self.URL, self.VALID, HTTP_X_TENANT_ID='no_such_tenant')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(DemoRequest.objects.count(), 0)

    def test_honeypot_is_accepted_but_discarded(self):
        payload = dict(self.VALID, note_ref='http://spam.example')
        with self.assertLogs('tenants.views', level='WARNING') as logged:
            response = Client().post(self.URL, payload)
        # Indistinguishable from success on the wire, and nothing stored -- but
        # it leaves a trace, because a false positive here throws away a real
        # lead behind a "thank you".
        self.assertEqual(response.status_code, 201)
        self.assertEqual(DemoRequest.objects.count(), 0)
        self.assertIn('honeypot', logged.output[0])
        self.assertIn(self.VALID['email'], logged.output[0])

    def test_form_page_uses_the_same_honeypot_field_name(self):
        """The page and the view have to agree, and nothing else would notice.

        If the two names drift apart the honeypot does not error -- it just
        stops catching anything, quietly, forever. Cheap to assert, and the
        failure it guards has no other symptom.
        """
        page = (Path(__file__).resolve().parent.parent
                / 'frontend' / 'site' / 'pages' / 'demo.html')
        self.assertIn(f'name="{HONEYPOT_FIELD}"', page.read_text())

    def test_honeypot_field_name_avoids_browser_autofill_tokens(self):
        # `company_url` matched Chrome's COMPANY autofill heuristic, which
        # ignores autocomplete="off". A browser filling it would have silently
        # binned a genuine submission.
        for token in ('company', 'organization', 'url', 'email', 'name', 'phone'):
            self.assertNotIn(token, HONEYPOT_FIELD)

    def test_malformed_forwarded_header_does_not_500(self):
        # The column is a Postgres inet and Django passes unparseable values
        # straight through, so an unvalidated header crashed the rate-limit
        # query -- a 500 on a public endpoint from one header.
        for bad in ('notanip', '203.0.113.9:54321', 'a:b:c', '<script>', ''):
            with self.subTest(forwarded=bad):
                response = Client().post(
                    self.URL, dict(self.VALID, email=f'x{abs(hash(bad))}@demo.test'),
                    HTTP_X_FORWARDED_FOR=bad,
                )
                self.assertEqual(response.status_code, 201)

    def test_junk_forwarded_header_is_not_a_way_around_the_rate_limit(self):
        # Falling back to REMOTE_ADDR matters: if a junk header meant "no
        # address", junk would be the bypass.
        client = Client()
        for i in range(6):
            response = client.post(
                self.URL, dict(self.VALID, email=f'junk{i}@demo.test'),
                HTTP_X_FORWARDED_FOR='not-an-address',
            )
        self.assertEqual(response.status_code, 429)

    def test_textarea_newlines_do_not_eat_the_length_budget(self):
        # A browser counts a line break as one character; form encoding sends
        # two. Without normalisation someone typing 2000 characters is told
        # their text is too long by a number they cannot see.
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

        # A different address is unaffected -- the limit is per client, not global.
        other = client.post(
            self.URL, dict(self.VALID, email='other@demo.test'),
            HTTP_X_FORWARDED_FOR='198.51.100.4',
        )
        self.assertEqual(other.status_code, 201)

    def test_spoofed_forwarded_chain_does_not_grant_a_fresh_quota(self):
        # Render appends the real peer, so the last entry is the honest one.
        # Prepending fake hops must not look like a new client.
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
    """Signup is where a boutique's identity is established, and it had no
    coverage at all. Schema creation is DDL, hence TransactionTestCase."""

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
        """App.jsx sets currentUser straight from this payload and never
        re-fetches, so an omitted role left a brand-new owner unable to assign
        any production stage for their whole first session.
        """
        try:
            response = self._signup('role.probe@ownerflow.test')
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(response.data['user']['role'], 'Owner')
        finally:
            self._drop('role.probe@ownerflow.test')

    def test_the_email_is_stored_lowercase_so_case_cannot_fork_a_boutique(self):
        """The duplicate check on owner_email is case-sensitive while
        django_tenants compares schema names case-insensitively, so a second
        signup differing only in case created an orphan tenant row whose
        CREATE SCHEMA had silently returned instead of raising.
        """
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
        """schema_name was the email with '@', '.' and '-' all flattened onto
        '_', so a.b@x.com and a-b@x.com landed on one schema.
        """
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
        """schema_name is varchar(63) and was exactly as long as the email."""
        long_email = ('x' * 60) + '@averylongdomainname.example.test'
        try:
            response = self._signup(long_email)
            self.assertEqual(response.status_code, 201, response.data)
            self.assertLessEqual(len(response.data['tenant_id']), 63)
        finally:
            self._drop(long_email)


class SignupBoutiqueIdentityTests(TransactionTestCase):
    """What the owner types about their boutique has to reach the documents
    their customers actually see."""

    def _drop(self, email):
        connection.set_schema_to_public()
        for tenant in BoutiqueTenant.objects.filter(owner_email=email.lower()):
            tenant.delete(force_drop=True)

    def test_the_boutiques_own_details_land_on_its_settings(self):
        """Signup collected a mobile number and discarded it, and created no
        BoutiqueSettings row at all -- so the row was conjured later by
        get_or_create(id=1) with its defaults, and every boutique's printed
        invoice claimed to be at "123 Atelier Way, Fashion District" on
        +91 9999999999.
        """
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
