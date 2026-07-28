from contextlib import contextmanager

from django.db import connection
from django.test import TransactionTestCase
from django_tenants.utils import schema_context
from rest_framework.test import APIClient

from crm_api.models import Customer
from tenants.models import BoutiqueTenant, Domain


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
