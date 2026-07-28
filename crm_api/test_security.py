"""Access control.

These assert the behaviour the platform should have. They are expected failures
today: DEFAULT_PERMISSION_CLASSES is AllowAny, so every business endpoint is
readable and writable with no credentials. Setting it to IsAuthenticated turns
them green -- treat a passing run here as the signal that the gap is closed, and
delete the expectedFailure markers at that point.
"""

import unittest

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

    @unittest.expectedFailure
    def test_client_directory_requires_authentication(self):
        response = self.client.get(reverse("customer-list"))
        self.assertIn(response.status_code, (401, 403))

    @unittest.expectedFailure
    def test_order_book_requires_authentication(self):
        response = self.client.get(reverse("order-list"))
        self.assertIn(response.status_code, (401, 403))

    @unittest.expectedFailure
    def test_revenue_dashboard_requires_authentication(self):
        response = self.client.get(reverse("dashboard"))
        self.assertIn(response.status_code, (401, 403))

    @unittest.expectedFailure
    def test_creating_a_client_requires_authentication(self):
        response = self.client.post(reverse("customer-list"), {
            "first_name": "Injected", "last_name": "Record",
            "mobile_number": "9600009999",
        }, format="json")
        self.assertIn(response.status_code, (401, 403))

    @unittest.expectedFailure
    def test_deleting_a_client_requires_authentication(self):
        response = self.client.delete(
            reverse("customer-detail", args=[self.customer.id]))
        self.assertIn(response.status_code, (401, 403))

    @unittest.expectedFailure
    def test_revenue_is_not_readable_without_authentication(self):
        response = self.client.get(reverse("customer-list"))
        if response.status_code == 200:
            # Today an anonymous caller reads name, mobile, address and spend.
            self.fail(
                "anonymous caller read client PII: "
                + str(response.json()[0]["mobile_number"])
            )
