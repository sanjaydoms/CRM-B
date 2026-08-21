"""An order names every garment on it, everywhere.

The regression these pin down: an order for a blouse and a lehenga was shown as
a blouse on the order summary, the invoice, all three staff dashboards, the
customer's WhatsApp confirmation, the tracking page and the analytics -- because
each of those read Customer.garment_type, a single field on the person that the
wizard overwrites with whichever dress was entered last. The customer was
invoiced for one of the two garments she had ordered.

Every surface now goes through domains.orders.garments, so these cover the
canonical helper, both order serializers, the confirmation message and the
tracking page, at one, two and three garments.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django_tenants.test.cases import TenantTestCase

from apps.catalog.models import GarmentJob, GarmentTemplate
from crm_api.models import BoutiqueSettings, Customer, CustomerMessage, Order
from crm_api.serializers import OrderSerializer, OrderSummarySerializer
from domains.orders.garments import garment_label, garment_names
from domains.orders.notifications import create_order_notifications
from domains.orders.repositories import OrderRepository


class GarmentNamingTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@garments.test"
        tenant.name = "Garment Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        from django.db import connection
        connection.set_tenant(self.tenant)

        User.objects.create_user(
            username="owner@garments.test", email="owner@garments.test",
            password="ownerpass123",
        )
        BoutiqueSettings.objects.get_or_create(id=1)

        self.customer = Customer.objects.create(
            first_name="Lakshmi", last_name="Iyer",
            mobile_number="919845012345", email_address="lakshmi@garments.test",
            address="44 Church Street", customer_type="Women",
            # The field every surface used to read. Deliberately set to something
            # that is NOT the whole truth, so a test that still reads it fails.
            garment_type="Blouse",
        )
        self.templates = {}
        for seq, (key, name) in enumerate([
            ('blouse', 'Blouse'), ('lehenga', 'Lehenga'), ('dupatta', 'Dupatta'),
        ]):
            self.templates[key] = GarmentTemplate.objects.create(
                key=key, name=name, version=1, sequence=seq,
            )

    def _order(self, order_id, garment_keys, measurements=None):
        order = Order.objects.create(
            order_id=order_id, customer=self.customer,
            total_amount=Decimal("32025.00"),
        )
        for seq, key in enumerate(garment_keys):
            GarmentJob.objects.create(
                order=order, template=self.templates[key], template_version=1,
                spec={}, sequence=seq,
                measurements=(measurements or {}).get(key, {}),
            )
        return OrderRepository.get_by_id(order.pk)

    # ---- the canonical helper -------------------------------------------

    def test_single_garment_order_names_that_garment(self):
        order = self._order("T2B-ONE", ['blouse'])
        self.assertEqual(garment_names(order), ['Blouse'])
        self.assertEqual(garment_label(order), 'Blouse')

    def test_two_garment_order_names_both(self):
        order = self._order("T2B-TWO", ['blouse', 'lehenga'])
        self.assertEqual(garment_names(order), ['Blouse', 'Lehenga'])
        self.assertEqual(garment_label(order), 'Blouse and Lehenga')

    def test_three_garment_order_names_all_three(self):
        order = self._order("T2B-THREE", ['blouse', 'lehenga', 'dupatta'])
        self.assertEqual(garment_names(order), ['Blouse', 'Lehenga', 'Dupatta'])
        self.assertEqual(garment_label(order), 'Blouse, Lehenga and Dupatta')

    def test_repeated_garment_type_is_listed_once_per_garment(self):
        """Two blouses on one order are two garments, not one."""
        order = self._order("T2B-PAIR", ['blouse', 'blouse'])
        self.assertEqual(garment_names(order), ['Blouse', 'Blouse'])

    def test_order_with_no_jobs_falls_back_to_the_customer_field(self):
        """Orders written before garment jobs existed still name their garment.

        Nine of the ten orders already in the database have no jobs, so the
        fallback is load-bearing rather than defensive.
        """
        order = OrderRepository.get_by_id(
            Order.objects.create(order_id="T2B-LEGACY", customer=self.customer).pk
        )
        self.assertEqual(garment_names(order), ['Blouse'])

    def test_order_with_no_jobs_and_no_customer_garment_type(self):
        self.customer.garment_type = ""
        self.customer.save(update_fields=['garment_type'])
        order = OrderRepository.get_by_id(
            Order.objects.create(order_id="T2B-BLANK", customer=self.customer).pk
        )
        self.assertEqual(garment_names(order), [])
        self.assertEqual(garment_label(order), 'Custom garment')

    # ---- the serializers every screen reads ------------------------------

    def test_order_serializer_carries_every_garment(self):
        order = self._order("T2B-SER", ['blouse', 'lehenga'])
        data = OrderSerializer(order).data
        self.assertEqual(data['garments'], ['Blouse', 'Lehenga'])
        self.assertEqual(data['garment_label'], 'Blouse and Lehenga')
        self.assertEqual(len(data['garment_jobs']), 2)

    def test_summary_serializer_carries_every_garment(self):
        """The dashboard panels name the garment too, and named the wrong one."""
        self._order("T2B-SUM", ['blouse', 'lehenga'])
        row = OrderSummarySerializer(
            OrderRepository.summary_queryset().get(order_id="T2B-SUM")
        ).data
        self.assertEqual(row['garments'], ['Blouse', 'Lehenga'])
        self.assertEqual(row['garment_label'], 'Blouse and Lehenga')

    def test_each_garment_keeps_its_own_measurements(self):
        """The blouse's waist is the blouse's, not whichever dress was last.

        The customer-level roll-up keeps one waist for the whole order, so a
        screen reading it shows the tailor the lehenga's waist for the blouse.
        """
        order = self._order(
            "T2B-MEAS", ['blouse', 'lehenga'],
            measurements={
                'blouse': {'waist': '30', 'blouse_length': '15', 'armhole': '16'},
                'lehenga': {'waist': '31', 'floor_length': '40'},
            },
        )
        jobs = {j['template_name']: j for j in OrderSerializer(order).data['garment_jobs']}
        self.assertEqual(jobs['Blouse']['measurements']['waist'], '30')
        self.assertEqual(jobs['Lehenga']['measurements']['waist'], '31')
        # Dimensions the roll-up drops entirely must survive on the job.
        self.assertEqual(jobs['Blouse']['measurements']['blouse_length'], '15')
        self.assertEqual(jobs['Blouse']['measurements']['armhole'], '16')
        self.assertEqual(jobs['Lehenga']['measurements']['floor_length'], '40')

    # ---- what the customer is actually told ------------------------------

    def test_confirmation_message_lists_every_garment(self):
        order = self._order("T2B-MSG", ['blouse', 'lehenga'])
        create_order_notifications(order, created=True)
        body = CustomerMessage.objects.get(order=order).body
        self.assertIn("Garments: Blouse and Lehenga", body)
        self.assertNotIn("Garment: Blouse\n", body)

    def test_confirmation_message_stays_singular_for_one_garment(self):
        order = self._order("T2B-MSG1", ['lehenga'])
        create_order_notifications(order, created=True)
        body = CustomerMessage.objects.get(order=order).body
        self.assertIn("Garment: Lehenga", body)

    def test_tracking_page_shows_every_garment(self):
        from domains.orders.tracking import tracking_url
        order = self._order("T2B-TRACK", ['blouse', 'lehenga'])
        path = tracking_url(order).split('/track/', 1)[1]
        response = self.client.get(f"/track/{path}")
        self.assertEqual(response.status_code, 200)
        page = response.content.decode()
        self.assertIn("Blouse", page)
        self.assertIn("Lehenga", page)
        self.assertIn("Garments", page)
