"""The customer-facing order number: #1, #2, #3 per boutique.

order_id (T2B-YYMMDD-NNNN) is untouched -- it is still the key every lookup,
token and cross-app reference uses. order_number is what gets printed.
"""
import threading

from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase
from django_tenants.utils import get_public_schema_name, get_tenant_model

from crm_api.models import BoutiqueSettings, Customer, Order
from crm_api.serializers import OrderSerializer
from crm_api.test_workflow import WorkflowTestBase
from domains.orders.services import OrderService
from domains.orders.tracking import build_token, read_token


class OrderNumberingTests(WorkflowTestBase):

    def test_orders_are_numbered_sequentially_from_one(self):
        first = self.make_order(customer=self.make_customer("9800000011"))
        second = self.make_order(customer=self.make_customer("9800000012"))
        third = self.make_order(customer=self.make_customer("9800000013"))
        self.assertEqual([first.order_number, second.order_number, third.order_number],
                         [1, 2, 3])
        self.assertEqual(first.reference, "#1")
        self.assertEqual(third.reference, "#3")

    def test_internal_id_and_tracking_token_are_unchanged(self):
        order = self.make_order()
        self.assertRegex(order.order_id, r"^T2B-\d{6}-")
        self.assertEqual(read_token(build_token(order)), (connection.schema_name, order.order_id))
        data = OrderSerializer(order).data
        self.assertEqual(data["order_id"], order.order_id)
        self.assertEqual(data["order_number"], 1)
        self.assertEqual(data["order_reference"], "#1")

    def test_notifications_and_messages_print_the_number(self):
        from crm_api.models import CustomerMessage, Notification
        order = self.make_order()
        self.assertIn("#1", Notification.objects.filter(recipient_role="Owner").first().title)
        self.assertIn("#1", CustomerMessage.objects.get(order=order).body)
        self.assertNotIn(order.order_id, CustomerMessage.objects.get(order=order).body)

    def test_a_row_without_a_number_falls_back_to_order_id(self):
        order = self.make_order()
        order.order_number = None
        self.assertEqual(order.reference, order.order_id)

    def test_backfill_numbers_historical_orders_oldest_first(self):
        from importlib import import_module
        from django.apps import apps
        migration = import_module('crm_api.migrations.0037_order_order_number')
        customer = self.make_customer()
        older = Order.objects.create(order_id="T2B-OLD-1", customer=customer)
        newer = Order.objects.create(order_id="T2B-OLD-2", customer=customer)
        migration.backfill(apps, None)
        older.refresh_from_db(); newer.refresh_from_db()
        self.assertEqual((older.order_number, newer.order_number), (1, 2))
        # And the service carries on from where the backfill stopped.
        self.assertEqual(self.make_order(customer=self.make_customer("9800000099")).order_number, 3)


class ConcurrentNumberingTests(TransactionTestCase):
    """Several counters placing orders at the same instant draw distinct numbers.

    TransactionTestCase, not TenantTestCase: the workers run on their own
    connections and can only see committed rows, and the row lock only means
    something when there are real concurrent transactions to serialise.
    """

    WORKERS = 6

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        call_command('migrate_schemas', schema_name=get_public_schema_name(),
                     interactive=False, verbosity=0)
        cls.tenant = get_tenant_model()(
            schema_name='test_numbering', owner_email='owner@numbering.test',
            name='Numbering Atelier')
        cls.tenant.save(verbosity=0)
        connection.set_tenant(cls.tenant)

    @classmethod
    def tearDownClass(cls):
        connection.set_schema_to_public()
        cls.tenant.delete(force_drop=True)
        super().tearDownClass()

    def setUp(self):
        connection.set_tenant(self.tenant)
        BoutiqueSettings.objects.get_or_create(id=1)

    def test_concurrent_creation_never_duplicates_a_number(self):
        gate = threading.Barrier(self.WORKERS)
        numbers, errors = [], []

        def place(i):
            connection.set_tenant(self.tenant)
            try:
                customer = Customer.objects.create(
                    first_name=f"C{i}", last_name="Test", mobile_number=f"98111000{i:02d}")
                gate.wait()
                order = OrderService.create_order_for_customer(
                    customer, {"base_price": 100}, notify=False)
                numbers.append(order.order_number)
            except Exception as exc:  # noqa: BLE001 - surfaced by the assertion below
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=place, args=(i,)) for i in range(self.WORKERS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        self.assertEqual(errors, [])
        self.assertEqual(sorted(numbers), list(range(1, self.WORKERS + 1)))
