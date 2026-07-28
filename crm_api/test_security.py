"""Access control.

Business endpoints require a token. These guard that: until recently every one
of them was readable and writable with no credentials at all, so an anonymous
caller could pull a boutique's whole client list -- names, phone numbers,
addresses, measurements and revenue -- and write to it.
"""

from django.contrib.auth.models import User
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from rest_framework.test import APIClient

from crm_api.models import Customer, Order


class UnauthenticatedAccessTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@security.test"
        tenant.name = "Security Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        from django.db import connection
        connection.set_tenant(self.tenant)
        User.objects.create_user(
            username="owner@security.test", email="owner@security.test",
            password="pass12345",
        )
        self.customer = Customer.objects.create(
            first_name="Private", last_name="Client", mobile_number="9600000001",
            address="12 Residential Road", email_address="private@client.test",
        )
        Order.objects.create(
            order_id="T2B-SEC-0001", customer=self.customer, total_amount=95000)
        # No credentials are set on this client -- only the tenant header.
        self.client = APIClient()
        self.client.credentials(HTTP_X_TENANT_ID=self.tenant.schema_name)

    def test_client_directory_requires_authentication(self):
        response = self.client.get(reverse("customer-list"))
        self.assertIn(response.status_code, (401, 403))

    def test_order_book_requires_authentication(self):
        response = self.client.get(reverse("order-list"))
        self.assertIn(response.status_code, (401, 403))

    def test_revenue_dashboard_requires_authentication(self):
        response = self.client.get(reverse("dashboard"))
        self.assertIn(response.status_code, (401, 403))

    def test_creating_a_client_requires_authentication(self):
        response = self.client.post(reverse("customer-list"), {
            "first_name": "Injected", "last_name": "Record",
            "mobile_number": "9600009999",
        }, format="json")
        self.assertIn(response.status_code, (401, 403))

    def test_deleting_a_client_requires_authentication(self):
        response = self.client.delete(
            reverse("customer-detail", args=[self.customer.id]))
        self.assertIn(response.status_code, (401, 403))

    def test_anonymous_caller_cannot_read_client_pii(self):
        """The concrete exposure: this used to return name, mobile and address."""
        response = self.client.get(reverse("customer-list"))
        self.assertNotEqual(response.status_code, 200)
        self.assertNotIn("12 Residential Road", response.content.decode())
