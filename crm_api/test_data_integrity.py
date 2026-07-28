"""Validation, derived values and API contract.

Covers the areas the original suite left open: input the API should reject,
figures the dashboard reports, and derived fields the interface presents as
client attributes.
"""

from django.contrib.auth.models import User
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from crm_api.models import Customer, Measurement, Order, Tailor
from crm_api.serializers import CustomerSummarySerializer
from domains.customers.repositories import CustomerRepository


class IntegrityTestBase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@integrity.test"
        tenant.name = "Integrity Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        from django.db import connection
        connection.set_tenant(self.tenant)
        self.user = User.objects.create_user(
            username="owner@integrity.test", email="owner@integrity.test",
            password="pass12345", first_name="Owner",
        )
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION="Token " + Token.objects.create(user=self.user).key,
            HTTP_X_TENANT_ID=self.tenant.schema_name,
        )


class CustomerValidationTests(IntegrityTestBase):
    def test_duplicate_mobile_number_is_rejected(self):
        Customer.objects.create(first_name="A", last_name="One", mobile_number="9111111111")
        response = self.client.post(reverse("customer-list"), {
            "first_name": "B", "last_name": "Two", "mobile_number": "9111111111",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("mobile_number", response.json())

    def test_missing_required_name_is_rejected(self):
        response = self.client.post(reverse("customer-list"), {
            "mobile_number": "9222222222",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_email_is_rejected(self):
        response = self.client.post(reverse("customer-list"), {
            "first_name": "C", "last_name": "Three",
            "mobile_number": "9333333333", "email_address": "definitely-not-an-email",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_creating_a_customer_always_creates_a_measurement_row(self):
        response = self.client.post(reverse("customer-list"), {
            "first_name": "D", "last_name": "Four", "mobile_number": "9444444444",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        customer = Customer.objects.get(mobile_number="9444444444")
        self.assertTrue(hasattr(customer, "measurements"))


class MeasurementHistoryTests(IntegrityTestBase):
    def test_history_is_written_once_per_actual_change(self):
        customer = Customer.objects.create(
            first_name="E", last_name="Five", mobile_number="9555555555")
        measurement = Measurement.objects.create(customer=customer, bust=34)
        self.assertEqual(customer.measurement_history.count(), 1)

        measurement.bust = 36
        measurement.save()
        self.assertEqual(customer.measurement_history.count(), 2)

    def test_saving_without_changing_anything_adds_no_history(self):
        customer = Customer.objects.create(
            first_name="F", last_name="Six", mobile_number="9666666666")
        measurement = Measurement.objects.create(customer=customer, bust=34)
        measurement.save()
        measurement.save()
        self.assertEqual(customer.measurement_history.count(), 1)


class SegmentAndSpendTests(IntegrityTestBase):
    def _customer_with_orders(self, mobile, amounts):
        customer = Customer.objects.create(
            first_name="G", last_name="Seven", mobile_number=mobile)
        for i, amount in enumerate(amounts):
            Order.objects.create(
                order_id=f"T2B-SEG-{mobile[-4:]}-{i}", customer=customer,
                total_amount=amount, payment_status="Paid",
            )
        return customer

    def _row(self, customer):
        obj = CustomerRepository.summary_queryset().get(pk=customer.pk)
        return CustomerSummarySerializer(obj).data

    def test_vip_by_lifetime_spend(self):
        row = self._row(self._customer_with_orders("9777777771", [80000]))
        self.assertEqual(row["segment"], "VIP")

    def test_vip_by_order_count(self):
        row = self._row(self._customer_with_orders("9777777772", [1000, 1000, 1000]))
        self.assertEqual(row["segment"], "VIP")

    def test_high_value_client(self):
        row = self._row(self._customer_with_orders("9777777773", [25000]))
        self.assertEqual(row["segment"], "HVC")

    def test_client_with_no_orders_is_general(self):
        row = self._row(self._customer_with_orders("9777777774", []))
        self.assertEqual(row["segment"], "General")
        self.assertEqual(row["total_spend"], 0)
        self.assertEqual(row["order_count"], 0)

    def test_spend_totals_every_order(self):
        row = self._row(self._customer_with_orders("9777777775", [1000, 2500, 500]))
        self.assertEqual(row["total_spend"], 4000.0)
        self.assertEqual(row["order_count"], 3)


class StyleDnaStabilityTests(IntegrityTestBase):
    def test_style_profile_is_stable_for_the_same_client(self):
        """A client's style profile must not change between processes.

        The colour and style fields were seeded from Python's built-in hash(),
        which is salted per process -- so the same client showed a different
        palette after every server restart.
        """
        import subprocess
        import sys

        customer = Customer.objects.create(
            first_name="H", last_name="Eight", mobile_number="9888888888")
        cid = str(customer.id)

        script = (
            "from crm_api.serializers import build_style_dna\n"
            "class C:\n"
            "    id = %r\n"
            "    garment_type = 'Lehenga'\n"
            "    created_at = __import__('django.utils.timezone', fromlist=['x']).now()\n"
            "    measurements = None\n"
            "d = build_style_dna(C())\n"
            "print(d['colors'] + '|' + d['style'])\n" % cid
        )
        results = set()
        for _ in range(3):
            out = subprocess.run(
                [sys.executable, "-c",
                 "import django,os;os.environ.setdefault('DJANGO_SETTINGS_MODULE',"
                 "'boutique_crm.settings');django.setup();" + script],
                capture_output=True, text=True, env={**__import__("os").environ,
                                                     "PYTHONHASHSEED": "random"},
            )
            results.add(out.stdout.strip())
        self.assertEqual(
            len(results), 1,
            f"style profile changed between processes: {results}",
        )


class DashboardFigureTests(IntegrityTestBase):
    def test_revenue_counts_paid_in_full_and_advances_on_partial(self):
        customer = Customer.objects.create(
            first_name="I", last_name="Nine", mobile_number="9999999901")
        Order.objects.create(order_id="T2B-REV-1", customer=customer,
                             payment_status="Paid", total_amount=10000, advance_paid=10000)
        Order.objects.create(order_id="T2B-REV-2", customer=customer,
                             payment_status="Partially Paid", total_amount=20000, advance_paid=5000)
        Order.objects.create(order_id="T2B-REV-3", customer=customer,
                             payment_status="Pending", total_amount=30000, advance_paid=0)

        stats = self.client.get(reverse("dashboard")).json()["stats"]
        self.assertEqual(stats["revenue"], 15000.0)
        self.assertEqual(stats["total_orders"], 3)
        self.assertEqual(stats["total_customers"], 1)

    def test_status_distribution_counts_each_status(self):
        customer = Customer.objects.create(
            first_name="J", last_name="Ten", mobile_number="9999999902")
        for i, st in enumerate(["Received", "Received", "Delivered"]):
            Order.objects.create(order_id=f"T2B-DIST-{i}", customer=customer, order_status=st)
        dist = self.client.get(reverse("dashboard")).json()["stats"]["status_distribution"]
        self.assertEqual(dist["Received"], 2)
        self.assertEqual(dist["Delivered"], 1)


class StaffAccountTests(IntegrityTestBase):
    def test_creating_a_tailor_with_an_email_creates_a_linked_login(self):
        response = self.client.post(reverse("tailor-list"), {
            "name": "Kiran Rao", "specialty": "Embroidery",
            "email": "kiran@integrity.test", "role": "Tailor",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        tailor = Tailor.objects.get(email="kiran@integrity.test")
        self.assertIsNotNone(tailor.user)
        self.assertEqual(tailor.user.email, "kiran@integrity.test")

    def test_tailor_without_an_email_gets_no_login(self):
        response = self.client.post(reverse("tailor-list"), {
            "name": "No Email", "specialty": "Cutting", "role": "Tailor",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(Tailor.objects.get(name="No Email").user)

    def test_two_tailors_with_similar_emails_get_distinct_usernames(self):
        self.client.post(reverse("tailor-list"), {
            "name": "One", "specialty": "A", "email": "same@a.test", "role": "Tailor",
        }, format="json")
        self.client.post(reverse("tailor-list"), {
            "name": "Two", "specialty": "B", "email": "same@b.test", "role": "Tailor",
        }, format="json")
        usernames = set(User.objects.filter(email__startswith="same@").values_list("username", flat=True))
        self.assertEqual(len(usernames), 2, "usernames collided")
