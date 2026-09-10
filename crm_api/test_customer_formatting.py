
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test import Client
from django_tenants.test.cases import TenantTestCase

from core.formatting import format_datetime, format_money
from crm_api.models import BoutiqueSettings, Customer, Order, OrderStage
from domains.orders.tracking import build_token


class CustomerFacingFormatTestBase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@fmt.test"
        tenant.name = "Formatting Atelier"
        tenant.timezone = 'Asia/Kolkata'
        return tenant

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        BoutiqueSettings.objects.get_or_create(
            id=1, defaults={'name': 'Formatting Atelier', 'phone': '9876500011'})
        self.owner = User.objects.create_user(
            username="owner@fmt.test", email="owner@fmt.test", password="ownerpass123")
        self.customer = Customer.objects.create(
            first_name="Nithya", last_name="Raman", mobile_number="919611044455")
        self.tenant.timezone = 'Asia/Kolkata'

    def an_order(self, total, paid, order_id="T2B-FMT-0001"):
        return Order.objects.create(
            order_id=order_id, customer=self.customer,
            total_amount=Decimal(total), amount_paid=Decimal(paid),
            advance_paid=Decimal(paid), payment_status='Partially Paid')

    def tracking_page(self, order):
        response = Client().get(f"/track/{build_token(order)}/")
        connection.set_tenant(self.tenant)
        return response


class MoneyOnCustomerSurfacesTests(CustomerFacingFormatTestBase):
    def test_the_tracking_page_uses_lakh_grouping_and_no_stray_paise(self):
        order = self.an_order('149875.00', '10000.00')
        page = self.tracking_page(order).content.decode()

        self.assertIn('₹1,49,875', page, 'lakh grouping, above the 99,999 line')
        self.assertIn('₹10,000', page)
        self.assertIn('₹1,39,875', page, 'balance agrees with total minus paid')
        self.assertNotIn('149875.00', page)
        payment_block = page.split('<h2>Payment</h2>')[-1].split('</section>')[0]
        self.assertNotIn('.00', payment_block)

    def test_paise_survive_where_they_exist(self):
        order = self.an_order('49875.50', '0')
        page = self.tracking_page(order).content.decode()
        self.assertIn('₹49,875.50', page)

    def test_the_page_agrees_with_the_shared_formatter(self):
        order = self.an_order('1234567.00', '234567.00')
        page = self.tracking_page(order).content.decode()
        for value in (order.total_amount, order.amount_paid,
                      order.total_amount - order.amount_paid):
            self.assertIn(format_money(value), page)

    def test_the_whatsapp_balance_matches_the_tracking_page(self):
        from crm_api.models import Notification
        from domains.orders.notifications import create_order_notifications

        order = self.an_order('149875.00', '10000.00')
        order.order_status = 'Delivered'
        order.save()
        Notification.objects.all().delete()
        create_order_notifications(order, created=False, status_changed=True)

        message = Notification.objects.filter(recipient_role='Customer').first()
        self.assertIsNotNone(message)
        balance = order.total_amount - order.amount_paid
        self.assertIn(format_money(balance), message.message)
        self.assertIn(format_money(balance),
                      self.tracking_page(order).content.decode(),
                      'the message and the page quote one debt')


class TimeOnCustomerSurfacesTests(CustomerFacingFormatTestBase):
    def test_a_utc_instant_is_shown_in_the_boutiques_local_time(self):
        order = self.an_order('1000', '0')
        OrderStage.objects.create(
            order=order, stage_key='pressing', stage_name='Pressing',
            status='COMPLETED', sequence=1,
            completed_at=datetime(2026, 8, 24, 9, 30, 17, tzinfo=dt_timezone.utc))

        page = self.tracking_page(order).content.decode()
        self.assertIn('24 Aug 2026, 3:00 PM', page)
        self.assertNotIn('9:30 AM', page, 'UTC must never reach the customer')

    def test_storage_stays_utc_after_the_page_is_rendered(self):
        order = self.an_order('1000', '0')
        stamp = datetime(2026, 8, 24, 9, 30, 17, tzinfo=dt_timezone.utc)
        stage = OrderStage.objects.create(
            order=order, stage_key='pressing', stage_name='Pressing',
            status='COMPLETED', sequence=1, completed_at=stamp)

        self.tracking_page(order)

        stage.refresh_from_db()
        self.assertEqual(stage.completed_at, stamp,
                         'presentation must not write a converted time back')

    def test_a_boutique_in_another_zone_reads_its_own_clock(self):
        self.tenant.timezone = 'Asia/Dubai'
        self.tenant.save()
        self.addCleanup(setattr, self.tenant, 'timezone', 'Asia/Kolkata')
        order = self.an_order('1000', '0')
        OrderStage.objects.create(
            order=order, stage_key='pressing', stage_name='Pressing',
            status='COMPLETED', sequence=1,
            completed_at=datetime(2026, 8, 24, 9, 30, tzinfo=dt_timezone.utc))

        page = self.tracking_page(order).content.decode()
        self.assertIn('1:30 PM', page)
        self.assertNotIn('3:00 PM', page)

    def test_the_datetime_on_the_page_matches_the_shared_formatter(self):
        order = self.an_order('1000', '0')
        stamp = datetime(2026, 8, 24, 9, 30, 17, tzinfo=dt_timezone.utc)
        OrderStage.objects.create(
            order=order, stage_key='pressing', stage_name='Pressing',
            status='COMPLETED', sequence=1, completed_at=stamp)
        self.assertIn(format_datetime(stamp, self.tenant),
                      self.tracking_page(order).content.decode())


class ApiExposesTheZoneTests(CustomerFacingFormatTestBase):
    def test_the_settings_endpoint_carries_the_boutiques_timezone(self):
        from rest_framework.authtoken.models import Token
        from rest_framework.test import APIClient

        token, _ = Token.objects.get_or_create(user=self.owner)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Token {token.key}',
                        HTTP_X_TENANT_ID=self.tenant.schema_name)
        response = api.get('/api/boutique-settings/')
        self.assertEqual(response.status_code, 200)
        data = response.data
        if isinstance(data, list):
            data = data[0]
        self.assertEqual(data['timezone'], 'Asia/Kolkata')
