"""Paging, and the two ways it goes quietly wrong.

The interesting failures here are not "does page 2 exist". They are:

  * a row appearing on two pages, or on none, because the queryset had no
    ORDER BY and PostgreSQL was free to answer in a different order each time;
  * a search that only searches the page you are standing on, which is what a
    client-side filter becomes the moment the list is paged.

Both are silent. Both produce a screen that looks right.
"""

from django.contrib.auth.models import User
from django.db import connection
from django_tenants.test.cases import TenantTestCase
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory

from auth_tokens.services import issue_access
from core.pagination import StandardPagination
from crm_api.models import BoutiqueSettings, Customer


class PaginationTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@paging.test"
        tenant.name = "Paging Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        self.owner = User.objects.create_user(
            username="owner@paging.test", email="owner@paging.test",
            password="ownerpass123")
        BoutiqueSettings.objects.get_or_create(id=1)
        for i in range(5):
            Customer.objects.create(
                first_name=f"Client{i}", last_name="Testcase",
                mobile_number=f"90000000{i:02d}")
        Customer.objects.create(first_name="Rukmini", last_name="Iyer",
                                mobile_number="9000000099")

        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {issue_access(self.owner).key}',
            HTTP_X_TENANT_ID=self.tenant.schema_name)

    def test_a_list_answers_the_paged_shape(self):
        response = self.client.get('/api/customers/')
        self.assertEqual(response.status_code, 200)
        for key in ('count', 'next', 'previous', 'results'):
            self.assertIn(key, response.data)
        self.assertEqual(response.data['count'], 6)
        self.assertEqual(len(response.data['results']), 6)
        self.assertIsNone(response.data['next'])

    def test_paging_covers_every_row_exactly_once(self):
        seen = []
        url = '/api/customers/?page_size=2'
        while url:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            seen.extend(str(row['id']) for row in response.data['results'])
            url = response.data['next']

        self.assertEqual(len(seen), 6)
        self.assertEqual(len(set(seen)), 6, 'a row was served on two pages')
        self.assertEqual(set(seen), {str(c.id) for c in Customer.objects.all()})

    def test_page_size_is_capped(self):
        """The parameter must not be a way to ask for the unbounded response
        this whole class exists to prevent."""
        asked_for = StandardPagination().get_page_size(
            Request(APIRequestFactory().get('/', {'page_size': '100000'})))
        self.assertEqual(asked_for, StandardPagination.max_page_size)

    def test_an_unordered_queryset_is_given_a_stable_order(self):
        paginator = StandardPagination()
        queryset = Customer.objects.all().order_by()
        self.assertFalse(queryset.ordered)

        page = paginator.paginate_queryset(
            queryset, Request(APIRequestFactory().get('/', {'page_size': '3'})))
        # The rows themselves matter less than the fact that the queryset the
        # paginator sliced was ordered at all -- an unordered LIMIT/OFFSET is
        # what serves a row twice.
        self.assertEqual(len(page), 3)
        self.assertTrue(paginator.page.paginator.object_list.ordered)

    def test_search_runs_on_the_server_and_pages(self):
        response = self.client.get('/api/customers/?search=Rukmini')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['first_name'], 'Rukmini')

    def test_search_and_paging_compose(self):
        response = self.client.get('/api/customers/?search=Client&page_size=2')
        self.assertEqual(response.data['count'], 5)
        self.assertEqual(len(response.data['results']), 2)
        self.assertIsNotNone(response.data['next'])

    def test_orders_are_searchable_by_the_customer_they_are_for(self):
        from crm_api.models import Order
        customer = Customer.objects.get(first_name='Rukmini')
        Order.objects.create(order_id='T2B-260101-0001', customer=customer)
        Order.objects.create(
            order_id='T2B-260101-0002',
            customer=Customer.objects.get(first_name='Client0'))

        response = self.client.get('/api/orders/?search=Rukmini')
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['order_id'], 'T2B-260101-0001')
