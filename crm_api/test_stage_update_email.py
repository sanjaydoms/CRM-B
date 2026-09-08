from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import connection
from django_tenants.test.cases import TenantTestCase

from crm_api.models import BoutiqueSettings, Customer, Order
from domains.orders.notifications import create_order_notifications
from domains.orders.emails import send_stage_update_email


class StageUpdateEmailTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@stage.test"
        tenant.name = "Stage Email Boutique"
        return tenant

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        BoutiqueSettings.objects.get_or_create(
            id=1, defaults={'name': 'Stage Email Boutique', 'phone': '9876500011'}
        )
        self.customer = Customer.objects.create(
            first_name="Priya",
            last_name="Sharma",
            mobile_number="919876543210",
            email_address="priya.sharma@example.com"
        )
        self.order = Order.objects.create(
            order_id="T2B-STAGE-001",
            customer=self.customer,
            total_amount=Decimal("5000.00"),
            amount_paid=Decimal("2500.00"),
            payment_status="Partially Paid",
            order_status="Design & Creation"
        )

    @patch("apps.email_service.services.email_job_service.EmailJobService.enqueue_job")
    def test_send_stage_update_email_queues_redis_job(self, mock_enqueue):
        with self.captureOnCommitCallbacks(execute=True):
            send_stage_update_email(
                self.order,
                stage_name="Pattern Cutting",
                custom_message="Your garment for order T2B-STAGE-001 is now in the Pattern Cutting stage. Our master tailors are crafting it!"
            )

        mock_enqueue.assert_called_once()
        args = mock_enqueue.call_args[0][0]
        self.assertEqual(args['recipients'], ["priya.sharma@example.com"])
        self.assertIn("T2B-STAGE-001", args['subject'])
        self.assertIn("Pattern Cutting", args['subject'])
        self.assertIn("priya.sharma@example.com", args['recipients'])
        self.assertIn("Pattern Cutting", args['html_message'])
        self.assertNotIn("Dear Priya,\n\nDear Priya", args['html_message'])
        self.assertIn("Track your order", args['html_message'])

    @patch("apps.email_service.services.email_job_service.EmailJobService.enqueue_job")
    def test_create_order_notifications_triggers_stage_email(self, mock_enqueue):
        self.order.order_status = "Design & Creation"
        self.order.save()
        with self.captureOnCommitCallbacks(execute=True):
            create_order_notifications(self.order, created=False, status_changed=True, stage_name="Pattern Cutting")

        mock_enqueue.assert_called_once()
        args = mock_enqueue.call_args[0][0]
        self.assertEqual(args['recipients'], ["priya.sharma@example.com"])
        self.assertIn("Pattern Cutting", args['subject'])
        self.assertIn("Pattern Cutting", args['html_message'])

