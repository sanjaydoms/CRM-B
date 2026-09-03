
from contextlib import contextmanager

from django.contrib.auth.models import User
from django.db import connection
from django.test import TransactionTestCase
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from crm_api.models import Customer, Order
from tenants.models import BoutiqueTenant, DemoRequest, Domain


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


def admin_client(username='platform@admin.test', password='platform-admin-pass'):
    connection.set_schema_to_public()
    User.objects.filter(username=username).delete()
    User.objects.create_superuser(username=username, email=username, password=password)
    client = APIClient()
    response = client.post('/api/superadmin/auth/login/',
                           {'username': username, 'password': password}, format='json')
    assert response.status_code == 200, response.content
    client.credentials(HTTP_AUTHORIZATION='Token ' + response.json()['token'])
    return client


class ConsoleAccessTests(TransactionTestCase):


    URL = '/api/superadmin/overview/'

    def setUp(self):
        connection.set_schema_to_public()

    def test_anonymous_is_refused(self):
        self.assertIn(APIClient().get(self.URL).status_code, (401, 403))

    def test_ordinary_public_user_is_refused(self):
        User.objects.filter(username='plain@user.test').delete()
        user = User.objects.create_user(username='plain@user.test', password='pw')
        token, _ = Token.objects.get_or_create(user=user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)
        self.assertEqual(client.get(self.URL).status_code, 403)

    def test_login_refuses_a_valid_non_superuser(self):
        User.objects.filter(username='plain2@user.test').delete()
        User.objects.create_user(username='plain2@user.test', password='correct-pw')
        response = APIClient().post(
            '/api/superadmin/auth/login/',
            {'username': 'plain2@user.test', 'password': 'correct-pw'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'Invalid administrator credentials.')
        self.assertNotIn('token', response.json())

    def test_a_boutiques_own_superuser_cannot_reach_the_console(self):
        with temporary_tenant('sa_rogue', 'owner@rogue.test', 'Rogue Atelier'):
            with schema_context('sa_rogue'):
                rogue = User.objects.create_superuser(
                    username='rogue@rogue.test', email='rogue@rogue.test', password='pw')
                tenant_token, _ = Token.objects.get_or_create(user=rogue)
                key = tenant_token.key

            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION='Token ' + key,
                               HTTP_X_TENANT_ID='sa_rogue')
            self.assertIn(client.get(self.URL).status_code, (401, 403))

    def test_console_ignores_a_tenant_header(self):
        with temporary_tenant('sa_header', 'owner@header.test', 'Header Atelier'):
            client = admin_client()
            client.credentials(
                HTTP_AUTHORIZATION=client._credentials['HTTP_AUTHORIZATION'],
                HTTP_X_TENANT_ID='sa_header')
            self.assertEqual(client.get(self.URL).status_code, 200)


class OverviewTests(TransactionTestCase):


    def setUp(self):
        connection.set_schema_to_public()
        DemoRequest.objects.all().delete()

    def test_totals_and_rows_agree_and_come_from_tenant_schemas(self):
        with temporary_tenant('sa_ov_a', 'a@ov.test', 'Atelier A'), \
                temporary_tenant('sa_ov_b', 'b@ov.test', 'Atelier B'):
            with schema_context('sa_ov_a'):
                customer = Customer.objects.create(
                    first_name='Gia', last_name='A', mobile_number='9000000011')
                Order.objects.create(order_id='OV-1', customer=customer,
                                     total_amount=1000, order_status='Received')
                Order.objects.create(order_id='OV-2', customer=customer,
                                     total_amount=500, order_status='Delivered')
            with schema_context('sa_ov_b'):
                Customer.objects.create(first_name='Hal', last_name='B',
                                        mobile_number='9000000012')

            DemoRequest.objects.create(name='Lead', boutique='B', email='l@l.test',
                                       phone='1', status='NEW')

            body = admin_client().get('/api/superadmin/overview/').json()

            rows = {r['schema_name']: r for r in body['boutiques']}
            self.assertEqual(rows['sa_ov_a']['orders'], 2)
            self.assertEqual(rows['sa_ov_a']['open_orders'], 1)  # Delivered is closed
            self.assertEqual(rows['sa_ov_a']['revenue'], 1500.0)
            self.assertEqual(rows['sa_ov_b']['customers'], 1)
            self.assertEqual(rows['sa_ov_b']['orders'], 0)

            self.assertEqual(body['totals']['customers'], 2)
            self.assertEqual(body['totals']['orders'], 2)
            self.assertEqual(body['totals']['revenue'], 1500)
            self.assertEqual(body['leads']['new'], 1)

    def test_public_schema_is_not_listed_as_a_boutique(self):
        BoutiqueTenant.objects.get_or_create(
            schema_name='public',
            defaults={'owner_email': 'registry@platform.test', 'name': 'Public'})
        body = admin_client().get('/api/superadmin/overview/').json()
        self.assertNotIn('public', [r['schema_name'] for r in body['boutiques']])


class SuspensionActionTests(TransactionTestCase):


    def setUp(self):
        connection.set_schema_to_public()

    def test_suspend_then_reactivate_shuts_the_boutique_out_and_back_in(self):
        with temporary_tenant('sa_susp', 'owner@susp2.test', 'Suspendable') as tenant:
            with schema_context('sa_susp'):
                staff = User.objects.create_user(username='probe@sa_susp')
                staff_token, _ = Token.objects.get_or_create(user=staff)
                key = staff_token.key

            def call_api():
                client = APIClient()
                client.credentials(HTTP_AUTHORIZATION='Token ' + key,
                                   HTTP_X_TENANT_ID='sa_susp')
                return client.get('/api/customers/').status_code

            console = admin_client()
            self.assertEqual(call_api(), 200)

            suspended = console.post('/api/superadmin/boutiques/sa_susp/suspend/')
            self.assertEqual(suspended.status_code, 200)
            self.assertIs(suspended.json()['is_active'], False)
            self.assertEqual(call_api(), 403)

            restored = console.post('/api/superadmin/boutiques/sa_susp/reactivate/')
            self.assertEqual(restored.status_code, 200)
            self.assertIs(restored.json()['is_active'], True)
            self.assertEqual(call_api(), 200)

            tenant.refresh_from_db()
            self.assertTrue(tenant.is_active)

    def test_suspending_an_unknown_boutique_is_a_404(self):
        response = admin_client().post('/api/superadmin/boutiques/no_such_thing/suspend/')
        self.assertEqual(response.status_code, 404)


class DataBrowserTests(TransactionTestCase):

    def setUp(self):
        connection.set_schema_to_public()

    def test_inventory_lists_business_models_and_excludes_credentials(self):
        with temporary_tenant('sa_data', 'owner@data.test', 'Data Atelier'):
            body = admin_client().get('/api/superadmin/boutiques/sa_data/data/').json()
            keys = {d['key'] for d in body['datasets']}

            self.assertIn('crm_api.customer', keys)
            self.assertIn('crm_api.order', keys)
            self.assertIn('inventory.inventoryitem', keys)
            self.assertIn('design_studio.designasset', keys)
            self.assertIn('auth.user', keys)

            self.assertNotIn('authtoken.token', keys)
            self.assertNotIn('authtoken.tokenproxy', keys)
            self.assertNotIn('contenttypes.contenttype', keys)
            self.assertNotIn('auth.permission', keys)

    def test_rows_come_from_the_named_boutique_only(self):
        with temporary_tenant('sa_data_a', 'a@data.test', 'Atelier A'), \
                temporary_tenant('sa_data_b', 'b@data.test', 'Atelier B'):
            with schema_context('sa_data_a'):
                Customer.objects.create(first_name='Kay', last_name='A',
                                        mobile_number='9000000021')
            with schema_context('sa_data_b'):
                Customer.objects.create(first_name='Lee', last_name='B',
                                        mobile_number='9000000022')

            console = admin_client()
            a = console.get('/api/superadmin/boutiques/sa_data_a/data/crm_api.customer/').json()
            b = console.get('/api/superadmin/boutiques/sa_data_b/data/crm_api.customer/').json()

            self.assertEqual([r['first_name'] for r in a['rows']], ['Kay'])
            self.assertEqual([r['first_name'] for r in b['rows']], ['Lee'])

    def test_password_hashes_are_never_returned(self):
        with temporary_tenant('sa_data_pw', 'owner@pw.test', 'Password Atelier'):
            with schema_context('sa_data_pw'):
                User.objects.create_user(username='staff@pw.test',
                                         password='a-real-password-hash-me')

            body = admin_client().get(
                '/api/superadmin/boutiques/sa_data_pw/data/auth.user/').json()
            row = next(r for r in body['rows'] if r['username'] == 'staff@pw.test')

            self.assertEqual(row['password'], '•' * 8)
            self.assertNotIn('pbkdf2', str(row['password']))
            self.assertNotIn('pbkdf2', str(body))

    def test_an_excluded_model_cannot_be_fetched_by_naming_it(self):
        with temporary_tenant('sa_data_tok', 'owner@tok.test', 'Token Atelier'):
            with schema_context('sa_data_tok'):
                user = User.objects.create_user(username='tok@tok.test')
                Token.objects.get_or_create(user=user)

            console = admin_client()
            for key in ('authtoken.token', 'authtoken.tokenproxy',
                        'contenttypes.contenttype', 'auth.permission'):
                response = console.get(
                    f'/api/superadmin/boutiques/sa_data_tok/data/{key}/')
                self.assertEqual(response.status_code, 404, key)

    def test_search_and_pagination(self):
        with temporary_tenant('sa_data_pg', 'owner@pg.test', 'Paging Atelier'):
            with schema_context('sa_data_pg'):
                for i in range(7):
                    Customer.objects.create(first_name=f'Cust{i}', last_name='Page',
                                            mobile_number=f'90000001{i:02d}')
                Customer.objects.create(first_name='Findme', last_name='Unique',
                                        mobile_number='9000000199')

            console = admin_client()
            page1 = console.get(
                '/api/superadmin/boutiques/sa_data_pg/data/crm_api.customer/'
                '?page=1&page_size=3').json()
            self.assertEqual(page1['count'], 8)
            self.assertEqual(page1['pages'], 3)
            self.assertEqual(len(page1['rows']), 3)

            page3 = console.get(
                '/api/superadmin/boutiques/sa_data_pg/data/crm_api.customer/'
                '?page=3&page_size=3').json()
            self.assertEqual(len(page3['rows']), 2)
            self.assertFalse({r['id'] for r in page1['rows']} & {r['id'] for r in page3['rows']})

            found = console.get(
                '/api/superadmin/boutiques/sa_data_pg/data/crm_api.customer/'
                '?q=Findme').json()
            self.assertEqual(found['count'], 1)
            self.assertEqual(found['rows'][0]['last_name'], 'Unique')

    def test_related_rows_render_as_names_not_ids(self):
        with temporary_tenant('sa_data_fk', 'owner@fk.test', 'Relation Atelier'):
            with schema_context('sa_data_fk'):
                customer = Customer.objects.create(first_name='Mira', last_name='R',
                                                   mobile_number='9000000031')
                Order.objects.create(order_id='FK-1', customer=customer,
                                     total_amount=250)

            body = admin_client().get(
                '/api/superadmin/boutiques/sa_data_fk/data/crm_api.order/').json()
            self.assertIn('Mira', body['rows'][0]['customer'])

    def test_the_browser_is_read_only(self):
        with temporary_tenant('sa_data_ro', 'owner@ro.test', 'Readonly Atelier'):
            console = admin_client()
            url = '/api/superadmin/boutiques/sa_data_ro/data/crm_api.customer/'
            for call in (console.post, console.patch, console.delete):
                self.assertEqual(call(url).status_code, 405)

    def test_unknown_boutique_is_a_404(self):
        response = admin_client().get('/api/superadmin/boutiques/no_such/data/')
        self.assertEqual(response.status_code, 404)


class LeadTests(TransactionTestCase):


    def setUp(self):
        connection.set_schema_to_public()
        DemoRequest.objects.all().delete()

    def test_status_and_notes_are_writable_and_the_rest_is_not(self):
        lead = DemoRequest.objects.create(name='Ira', boutique='Ira Couture',
                                          email='ira@lead.test', phone='9', status='NEW')
        response = admin_client().patch(
            f'/api/superadmin/leads/{lead.id}/',
            {'status': 'CONTACTED', 'notes': 'Called Tuesday.',
             'email': 'attacker@evil.test'},
            format='json')
        self.assertEqual(response.status_code, 200)

        lead.refresh_from_db()
        self.assertEqual(lead.status, 'CONTACTED')
        self.assertEqual(lead.notes, 'Called Tuesday.')
        self.assertEqual(lead.email, 'ira@lead.test')

    def test_leads_cannot_be_created_or_deleted_through_the_console(self):
        lead = DemoRequest.objects.create(name='Jo', boutique='Jo Ltd',
                                          email='jo@lead.test', phone='8')
        console = admin_client()
        self.assertEqual(console.post('/api/superadmin/leads/', {}, format='json').status_code, 405)
        self.assertEqual(console.delete(f'/api/superadmin/leads/{lead.id}/').status_code, 405)
        self.assertTrue(DemoRequest.objects.filter(pk=lead.pk).exists())


import datetime

from superadmin.metrics import (
    CLOSED_ORDER_STATUSES, operational_metrics, platform_totals, tenant_metrics,
)


class ConsoleOrderMetricsTests(TransactionTestCase):

    def setUp(self):
        connection.set_schema_to_public()

    @staticmethod
    def _customer():
        return Customer.objects.create(first_name='Nia', last_name='Metric',
                                       mobile_number='9000000041')

    def test_settled_means_what_the_boutique_means_by_settled(self):
        from crm_api.views import OrderViewSet
        from domains.orders.services import _SETTLED_ORDER_STATUSES

        self.assertEqual(CLOSED_ORDER_STATUSES, _SETTLED_ORDER_STATUSES)
        self.assertIn('Shipped', CLOSED_ORDER_STATUSES)
        self.assertNotIn('Cancelled', OrderViewSet.CLIENT_STATUSES)
        for value in CLOSED_ORDER_STATUSES:
            self.assertIn(value, OrderViewSet.CLIENT_STATUSES)

    def test_a_shipped_order_is_counted_as_settled_not_open(self):
        with temporary_tenant('sa_met_ship', 'ship@met.test', 'Shipping Atelier') as tenant:
            with schema_context('sa_met_ship'):
                customer = self._customer()
                for order_id, order_status in (('ME-1', 'Received'),
                                               ('ME-2', 'Shipped'),
                                               ('ME-3', 'Delivered')):
                    Order.objects.create(order_id=order_id, customer=customer,
                                         total_amount=100, order_status=order_status)

            metrics = tenant_metrics(tenant)
            self.assertEqual(metrics['orders'], 3)
            self.assertEqual(metrics['open_orders'], 1)

    def test_booked_and_collected_are_different_numbers(self):
        with temporary_tenant('sa_met_cash', 'cash@met.test', 'Cashflow Atelier') as tenant:
            with schema_context('sa_met_cash'):
                customer = self._customer()
                Order.objects.create(order_id='MC-1', customer=customer,
                                     total_amount=1000, amount_paid=250,
                                     payment_status='Partially Paid')
                Order.objects.create(order_id='MC-2', customer=customer,
                                     total_amount=500, amount_paid=500,
                                     payment_status='Paid')

            metrics = tenant_metrics(tenant)
            self.assertEqual(float(metrics['revenue']), 1500.0)
            self.assertEqual(float(metrics['collected']), 750.0)
            self.assertNotEqual(metrics['revenue'], metrics['collected'])

            totals = platform_totals([tenant])
            self.assertEqual(float(totals['revenue']), 1500.0)
            self.assertEqual(float(totals['collected']), 750.0)

    def test_overdue_excludes_orders_that_are_already_gone(self):
        past = datetime.date.today() - datetime.timedelta(days=3)
        future = datetime.date.today() + datetime.timedelta(days=3)

        with temporary_tenant('sa_met_late', 'late@met.test', 'Late Atelier') as tenant:
            with schema_context('sa_met_late'):
                customer = self._customer()
                Order.objects.create(order_id='ML-1', customer=customer,
                                     order_status='Received', estimated_delivery=past)
                Order.objects.create(order_id='ML-2', customer=customer,
                                     order_status='Delivered', estimated_delivery=past)
                Order.objects.create(order_id='ML-3', customer=customer,
                                     order_status='Shipped', estimated_delivery=past)
                Order.objects.create(order_id='ML-4', customer=customer,
                                     order_status='Received', estimated_delivery=future)
                Order.objects.create(order_id='ML-5', customer=customer,
                                     order_status='Received', estimated_delivery=None)

            ops = operational_metrics(tenant)
            self.assertTrue(ops['healthy'])
            self.assertEqual(ops['overdue']['count'], 1)
            self.assertIn('order_date + 15 days', ops['overdue']['caveat'])

    def test_status_buckets_account_for_every_order(self):
        from crm_api.views import OrderViewSet

        with temporary_tenant('sa_met_bkt', 'bkt@met.test', 'Bucket Atelier') as tenant:
            with schema_context('sa_met_bkt'):
                customer = self._customer()
                for order_id, order_status in (('MB-1', 'Received'),
                                               ('MB-2', 'Received'),
                                               ('MB-3', 'Quality Check'),
                                               ('MB-4', 'Delivered'),
                                               ('MB-5', 'Totally Made Up')):
                    Order.objects.create(order_id=order_id, customer=customer,
                                         total_amount=10, order_status=order_status)

            ops = operational_metrics(tenant)
            buckets = ops['by_order_status']

            self.assertEqual(ops['orders'], 5)
            self.assertEqual(sum(buckets.values()), 5)
            self.assertEqual(buckets['Received'], 2)
            self.assertEqual(buckets['Shipped'], 0)
            self.assertEqual(buckets['Totally Made Up'], 1)
            for value in OrderViewSet.CLIENT_STATUSES:
                self.assertIn(value, buckets)

            self.assertEqual(sum(ops['by_payment_status'].values()), 5)
            self.assertEqual(ops['by_payment_status']['Paid'], 0)
            self.assertEqual(sum(ops['by_production_status'].values()), 5)
            self.assertEqual(sum(ops['by_stage'].values()), 5)

    def test_created_buckets_and_queued_messages(self):
        with temporary_tenant('sa_met_new', 'new@met.test', 'Fresh Atelier') as tenant:
            with schema_context('sa_met_new'):
                from crm_api.models import CustomerMessage

                customer = self._customer()
                order = Order.objects.create(order_id='MN-1', customer=customer,
                                             total_amount=10)
                CustomerMessage.objects.create(order=order, template_key='order_confirmation',
                                               to_number='9000000041', body='hi')
                CustomerMessage.objects.create(order=order, template_key='stage_update',
                                               to_number='9000000041', body='sent',
                                               status='SENT')

            ops = operational_metrics(tenant)
            self.assertEqual(ops['created'], {'today': 1, 'week': 1, 'month': 1})
            self.assertEqual(ops['queued_messages'], 1)

    def test_an_unreadable_boutique_reports_itself_rather_than_raising(self):
        tenant, _ = BoutiqueTenant.objects.get_or_create(
            schema_name='public',
            defaults={'owner_email': 'registry@platform.test', 'name': 'Public'})
        ops = operational_metrics(tenant)
        self.assertFalse(ops['healthy'])
        self.assertIsNone(ops['orders'])
        self.assertEqual(ops['by_order_status'], {})
