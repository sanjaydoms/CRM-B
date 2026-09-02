
from django.contrib.auth.models import User
from django_tenants.test.cases import TenantTestCase

from apps.design_studio.models import Designer
from core.roles import DESIGNER, OWNER, resolve_user_role
from crm_api.models import Tailor


class ResolveUserRoleTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@roles.test"
        tenant.name = "Roles Test Boutique"
        return tenant

    def setUp(self):
        super().setUp()
        from django.db import connection
        connection.set_tenant(self.tenant)

    def test_anonymous_has_no_role(self):
        self.assertIsNone(resolve_user_role(None))

        class Anonymous:
            is_authenticated = False
        self.assertIsNone(resolve_user_role(Anonymous()))

    def test_superuser_is_owner_regardless_of_profile(self):
        boss = User.objects.create_superuser(
            username="boss@roles.test", email="boss@roles.test", password="x")
        self.assertEqual(resolve_user_role(boss), OWNER)

    def test_a_tailor_profile_reports_its_own_role(self):
        user = User.objects.create_user(username="tailor@roles.test", password="x")
        Tailor.objects.create(name="Ravi", specialty="Bridal", role="Master", user=user)
        self.assertEqual(resolve_user_role(user), "Master")

    def test_a_designer_profile_reports_designer(self):
        user = User.objects.create_user(username="designer@roles.test", password="x")
        Designer.objects.create(name="Priya", user=user)
        self.assertEqual(resolve_user_role(user), DESIGNER)

    def test_no_profile_at_all_falls_back_to_owner(self):
        user = User.objects.create_user(username="plain@roles.test", password="x")
        self.assertEqual(resolve_user_role(user), OWNER)

    def test_a_tailor_profile_wins_over_a_designer_profile(self):
        user = User.objects.create_user(username="both@roles.test", password="x")
        Tailor.objects.create(name="Anita", specialty="Bridal", role="Tailor", user=user)
        Designer.objects.create(name="Anita", user=user)
        self.assertEqual(resolve_user_role(user), "Tailor")

    def test_a_designer_only_account_is_never_reported_as_owner(self):
        user = User.objects.create_user(username="designer2@roles.test", password="x")
        Designer.objects.create(name="Ravi", user=user)
        self.assertNotEqual(resolve_user_role(user), OWNER)
        self.assertEqual(resolve_user_role(user), DESIGNER)


class ApiRoleBoundaryTests(TenantTestCase):

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@perm.test"
        tenant.name = "Permission Test Boutique"
        return tenant

    def setUp(self):
        super().setUp()
        from django.db import connection
        from rest_framework.authtoken.models import Token
        from rest_framework.test import APIClient

        from crm_api.models import Customer, Order

        connection.set_tenant(self.tenant)

        def account(username, tailor=None):
            user = User.objects.create_user(username=username, password='pw12345678')
            if tailor is not None:
                tailor.user = user
                tailor.save()
            client = APIClient()
            client.credentials(
                HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=user).key}',
                HTTP_X_TENANT_ID=self.tenant.schema_name)
            return client

        self.rohit = Tailor.objects.create(name='Rohit', role='Tailor')
        self.anya = Tailor.objects.create(name='Anya', role='Master')

        self.owner = account('owner@perm.test')
        self.tailor = account('rohit@perm.test', self.rohit)
        self.master = account('anya@perm.test', self.anya)

        mine = Customer.objects.create(first_name='Mine', last_name='C', mobile_number='9000000001')
        theirs = Customer.objects.create(first_name='Theirs', last_name='C', mobile_number='9000000002')
        self.my_order = Order.objects.create(order_id='PERM-1', customer=mine, tailor=self.rohit)
        Order.objects.create(order_id='PERM-2', customer=theirs)


    def test_a_tailor_sees_only_their_own_orders(self):
        rows = self.tailor.get('/api/orders/').data
        self.assertEqual([r['order_id'] for r in rows], ['PERM-1'])

    def test_a_tailor_sees_only_the_customers_behind_their_orders(self):
        rows = self.tailor.get('/api/customers/').data
        self.assertEqual([r['first_name'] for r in rows], ['Mine'])

    def test_an_owner_sees_everything(self):
        self.assertEqual(len(self.owner.get('/api/orders/').data), 2)
        self.assertEqual(len(self.owner.get('/api/customers/').data), 2)

    def test_a_master_supervises_the_floor(self):
        self.assertEqual(len(self.master.get('/api/orders/').data), 2)


    def test_a_tailor_cannot_create_a_customer(self):
        response = self.tailor.post('/api/customers/', {
            'first_name': 'Nope', 'last_name': 'X', 'mobile_number': '9000000003'})
        self.assertEqual(response.status_code, 403)

    def test_a_tailor_cannot_touch_inventory(self):
        for path, payload in [
            ('/api/inventory/items/', {'item_code': 'X', 'name': 'X',
                                       'category': 'FABRIC', 'unit': 'METER'}),
            ('/api/inventory/suppliers/', {'name': 'Rogue'}),
        ]:
            self.assertEqual(self.tailor.post(path, payload, format='json').status_code, 403, path)

    def test_a_tailor_cannot_read_the_financial_reports(self):
        for report in ('cost-per-order', 'stock-position', 'suppliers'):
            self.assertEqual(
                self.tailor.get(f'/api/inventory/reports/{report}/').status_code, 403, report)

    def test_the_owner_can_read_the_financial_reports(self):
        self.assertEqual(self.owner.get('/api/inventory/reports/stock-position/').status_code, 200)

    def test_a_tailor_cannot_assign_work_to_others(self):
        response = self.tailor.post(
            f'/api/orders/{self.my_order.id}/assign-stage/',
            {'stage_key': 'stitching_in_progress', 'tailor_id': self.rohit.id}, format='json')
        self.assertEqual(response.status_code, 403)


    def test_a_tailor_can_still_advance_their_own_stage(self):
        response = self.tailor.post(
            f'/api/orders/{self.my_order.id}/transition/',
            {'stage_key': 'stitching_in_progress', 'status': 'COMPLETED'}, format='json')
        self.assertNotEqual(response.status_code, 403,
                            'a tailor must be able to advance their own stage')

    def test_anonymous_callers_get_nothing(self):
        from rest_framework.test import APIClient
        anon = APIClient()
        for path in ('/api/orders/', '/api/customers/', '/api/inventory/items/'):
            self.assertIn(anon.get(path).status_code, (401, 403), path)

    def test_a_designer_keeps_the_studio_and_loses_everything_else(self):
        from rest_framework.authtoken.models import Token
        from rest_framework.test import APIClient

        from apps.design_studio.models import Designer

        user = User.objects.create_user(username='designer@perm.test', password='pw12345678')
        Designer.objects.create(name='Dee', user=user)
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=user).key}',
            HTTP_X_TENANT_ID=self.tenant.schema_name)

        self.assertEqual(client.get('/api/design-studio/assets/').status_code, 200)
        for denied in ('/api/customers/', '/api/orders/', '/api/inventory/items/',
                       '/api/inventory/reports/stock-position/'):
            self.assertEqual(client.get(denied).status_code, 403, denied)
