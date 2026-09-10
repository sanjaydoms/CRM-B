from django_tenants.test.cases import TenantTestCase
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from rest_framework import status
from crm_api.models import BoutiqueSettings, Customer, Order, Tailor
from core.roles import OWNER


class InvoiceTemplateApiTests(TenantTestCase):

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@atelier.com"
        tenant.name = "Invoice Test Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        from django.db import connection
        connection.set_tenant(self.tenant)

        # Create Owner User
        self.owner_user = User.objects.create_user(
            username='owner_test', password='password123', email='owner@atelier.com'
        )
        self.owner_tailor = Tailor.objects.create(
            name='Owner Test', role=OWNER, user=self.owner_user
        )

        # Create Non-Owner User (Tailor)
        self.tailor_user = User.objects.create_user(
            username='tailor_test', password='password123', email='tailor@atelier.com'
        )
        self.tailor_profile = Tailor.objects.create(
            name='Tailor Test', role='Tailor', user=self.tailor_user
        )

        # Create Customer
        self.customer = Customer.objects.create(
            first_name='Priya', last_name='Sharma', mobile_number='9876543210'
        )

    def client_for(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        api = APIClient()
        api.credentials(
            HTTP_AUTHORIZATION=f'Token {token.key}',
            HTTP_X_TENANT_ID=self.tenant.schema_name,
            HTTP_HOST=getattr(self.tenant, 'domain_url', None) or 'testserver'
        )
        return api

    def test_owner_can_get_invoice_template_settings(self):
        client = self.client_for(self.owner_user)
        response = client.get('/api/settings/invoice-template/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['template'], 'classic')
        self.assertEqual(len(response.data['templates']), 3)

    def test_owner_can_update_invoice_template(self):
        client = self.client_for(self.owner_user)
        response = client.patch('/api/settings/invoice-template/', {'template': 'modern'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['template'], 'modern')

        # Verify DB updated
        config = BoutiqueSettings.objects.first()
        self.assertEqual(config.invoice_template, 'modern')

    def test_invalid_template_code_returns_400(self):
        client = self.client_for(self.owner_user)
        response = client.patch('/api/settings/invoice-template/', {'template': 'invalid_code'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'], 'Invalid invoice template.')

    def test_non_owner_cannot_get_or_update_invoice_template(self):
        client = self.client_for(self.tailor_user)

        # GET check
        get_resp = client.get('/api/settings/invoice-template/')
        self.assertEqual(get_resp.status_code, status.HTTP_403_FORBIDDEN)

        # PATCH check
        patch_resp = client.patch('/api/settings/invoice-template/', {'template': 'modern'}, format='json')
        self.assertEqual(patch_resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_new_orders_store_current_boutique_template_and_historical_orders_remain_unchanged(self):
        config, _ = BoutiqueSettings.objects.get_or_create(id=1)
        config.invoice_template = 'classic'
        config.save()

        # Order 1 created while setting is 'classic'
        order1 = Order.objects.create(order_id='INV-TEST-001', customer=self.customer)
        self.assertEqual(order1.invoice_template, 'classic')

        # Change boutique setting to 'modern'
        config.invoice_template = 'modern'
        config.save()

        # Order 2 created while setting is 'modern'
        order2 = Order.objects.create(order_id='INV-TEST-002', customer=self.customer)
        self.assertEqual(order2.invoice_template, 'modern')

        # Verify Order 1 still has 'classic'
        order1.refresh_from_db()
        self.assertEqual(order1.invoice_template, 'classic')
