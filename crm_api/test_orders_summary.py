"""The order figures, computed where they can stay correct.

Every number here used to be a `.reduce()` in the browser over whatever orders
it had downloaded. That works exactly as long as the browser downloads all of
them -- which is what made the order list impossible to page without quietly
turning the boutique's revenue into the revenue of page one.

So these tests are less about arithmetic than about the two properties that
arithmetic has to keep: it covers the WHOLE book regardless of paging, and it
covers only what the caller is allowed to see.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django_tenants.test.cases import TenantTestCase
from rest_framework.test import APIClient

from apps.catalog.models import GarmentJob, GarmentTemplate
from auth_tokens.services import issue_access
from crm_api.models import BoutiqueSettings, Customer, Order, Tailor


class OrderSummaryTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@summary.test"
        tenant.name = "Summary Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        BoutiqueSettings.objects.get_or_create(id=1)

        self.owner = User.objects.create_user(
            username="owner@summary.test", email="owner@summary.test",
            password="ownerpass123")
        self.tailor_user = User.objects.create_user(
            username="ravi@summary.test", email="ravi@summary.test",
            password="tailorpass123")
        self.ravi = Tailor.objects.create(
            name="Ravi", specialty="Stitching", role="Tailor",
            email="ravi@summary.test", user=self.tailor_user)

        self.blouse = GarmentTemplate.objects.create(key='blouse', name='Blouse')
        self.lehenga = GarmentTemplate.objects.create(key='lehenga', name='Lehenga')

        anjali = Customer.objects.create(first_name="Anjali", last_name="Rao",
                                         mobile_number="9812345671")
        divya = Customer.objects.create(first_name="Divya", last_name="Nair",
                                        mobile_number="9812345672")

        # Ravi's order: two garments, part paid.
        self.ravis = Order.objects.create(
            order_id='SUM-1', customer=anjali, tailor=self.ravi,
            total_amount=Decimal('10000'), amount_paid=Decimal('4000'),
            payment_status='Partially Paid', order_status='Design & Creation')
        self.job(self.ravis, self.blouse, 1,
                 {'front_neck': 'sweetheart', 'sleeve_length': 'elbow'})
        self.job(self.ravis, self.lehenga, 2, {})

        # Somebody else's order, fully paid.
        self.other = Order.objects.create(
            order_id='SUM-2', customer=divya,
            total_amount=Decimal('5000'), amount_paid=Decimal('5000'),
            payment_status='Paid', order_status='Delivered')
        self.job(self.other, self.blouse, 1, {'front_neck': 'sweetheart'})

    def job(self, order, template, sequence, spec):
        return GarmentJob.objects.create(
            order=order, template=template, template_version=template.version,
            sequence=sequence, spec=spec)

    def as_user(self, user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {issue_access(user).key}',
                           HTTP_X_TENANT_ID=self.tenant.schema_name)
        return client

    # --- the money ---------------------------------------------------------

    def test_the_owner_sees_the_whole_book(self):
        data = self.as_user(self.owner).get('/api/orders/summary/').data
        self.assertEqual(data['count'], 2)
        self.assertEqual(data['billed'], 15000.0)
        self.assertEqual(data['collected'], 9000.0)
        self.assertEqual(data['outstanding'], 6000.0)
        self.assertEqual(data['average_order_value'], 7500.0)

    def test_collected_is_money_received_not_the_value_of_paid_orders(self):
        """A part-paid order contributes what was actually paid. Counting it as
        zero collected and its full value as outstanding was wrong in both
        directions at once, which is why the client comment says so."""
        data = self.as_user(self.owner).get('/api/orders/summary/').data
        self.assertEqual(data['collected'], 4000.0 + 5000.0)

    def test_the_totals_do_not_depend_on_how_many_rows_the_client_holds(self):
        """The whole point. One row per page, and the totals are unchanged."""
        client = self.as_user(self.owner)
        page = client.get('/api/orders/?page_size=1').data
        self.assertEqual(len(page['results']), 1)
        self.assertEqual(page['count'], 2)

        data = client.get('/api/orders/summary/').data
        self.assertEqual(data['count'], 2)
        self.assertEqual(data['billed'], 15000.0)
        self.assertEqual(data['collected'], 9000.0)

    # --- the garment breakdowns -------------------------------------------

    def test_garments_are_counted_per_garment_not_per_order(self):
        data = self.as_user(self.owner).get('/api/orders/summary/').data
        self.assertEqual(data['garments'], {'Blouse': 2, 'Lehenga': 1})
        self.assertEqual(data['garment_total'], 3)

    def test_spec_values_come_back_raw_for_the_client_to_label(self):
        data = self.as_user(self.owner).get('/api/orders/summary/').data
        self.assertEqual(data['necklines'], {'sweetheart': 2})
        self.assertEqual(data['sleeves'], {'elbow': 1})

    def test_status_counts_are_per_order_not_per_stage(self):
        """The stages join multiplies each order by its stage rows; an
        unqualified count made every bucket fifteen times too big on a tailor's
        dashboard, which the dashboard endpoint's own comment records."""
        data = self.as_user(self.owner).get('/api/orders/summary/').data
        self.assertEqual(data['status_counts'],
                         {'Design & Creation': 1, 'Delivered': 1})

    # --- scoping -----------------------------------------------------------

    def test_a_tailor_totals_only_their_own_work(self):
        data = self.as_user(self.tailor_user).get('/api/orders/summary/').data
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['billed'], 10000.0)
        self.assertEqual(data['garments'], {'Blouse': 1, 'Lehenga': 1})

    def test_an_empty_book_is_zeroes_rather_than_a_division_by_zero(self):
        Order.objects.all().delete()
        data = self.as_user(self.owner).get('/api/orders/summary/').data
        self.assertEqual(
            (data['count'], data['billed'], data['average_order_value']),
            (0, 0.0, 0.0))


class OrderFilterTests(OrderSummaryTests):
    """The Orders and Invoices tabs' filter buttons, applied by the server.

    Client-side they filtered whatever had been downloaded; against a paged list
    that is not a filter at all.
    """

    def rows(self, query):
        return self.as_user(self.owner).get(f'/api/orders/?{query}').data['results']

    def test_active_excludes_shipped_and_delivered(self):
        self.assertEqual([r['order_id'] for r in self.rows('status_group=active')],
                         ['SUM-1'])

    def test_delivered_selects_only_delivered(self):
        self.assertEqual([r['order_id'] for r in self.rows('status_group=delivered')],
                         ['SUM-2'])

    def test_open_keeps_dispatched_work_and_drops_delivered(self):
        """The superset the two 'active work' panels filter down from."""
        self.other.order_status = 'Shipped'
        self.other.save(update_fields=['order_status'])
        self.assertEqual({r['order_id'] for r in self.rows('status_group=open')},
                         {'SUM-1', 'SUM-2'})

        self.other.order_status = 'Delivered'
        self.other.save(update_fields=['order_status'])
        self.assertEqual([r['order_id'] for r in self.rows('status_group=open')],
                         ['SUM-1'])

    def test_an_unknown_group_narrows_nothing(self):
        """An empty screen that looks like a boutique with no orders is the
        worst possible answer to a value we do not recognise."""
        data = self.as_user(self.owner).get('/api/orders/?status_group=whatever').data
        self.assertEqual(data['count'], 2)

    def test_pending_includes_part_paid_invoices(self):
        """They are exactly the ones somebody opens this screen to chase."""
        self.assertEqual([r['order_id'] for r in self.rows('payment=pending')],
                         ['SUM-1'])

    def test_paid_selects_only_settled_invoices(self):
        self.assertEqual([r['order_id'] for r in self.rows('payment=paid')],
                         ['SUM-2'])

    def test_a_group_and_a_search_compose(self):
        self.assertEqual(
            [r['order_id'] for r in self.rows('status_group=active&search=Anjali')],
            ['SUM-1'])

    def test_a_filtered_search_that_matches_nothing_is_empty_not_everything(self):
        data = self.as_user(self.owner).get(
            '/api/orders/?status_group=delivered&search=Anjali').data
        self.assertEqual(data['count'], 0)
        self.assertEqual(data['results'], [])
