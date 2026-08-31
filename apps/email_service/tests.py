from django.contrib.auth.models import User
from django.core import mail
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient


class MultiRecipientEmailAPITest(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "testowner@example.com"
        tenant.name = "Test Boutique"
        return tenant

    def setUp(self):
        super().setUp()
        from django.db import connection
        connection.set_tenant(self.tenant)

        self.user = User.objects.create_user(
            username="emailtestuser", email="user@example.com", password="password123"
        )
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.token.key}',
            HTTP_X_TENANT_ID=self.tenant.schema_name,
        )

    def test_send_bulk_email_success(self):
        url = reverse('send-bulk-email')
        payload = {
            "recipients": [
                "sadasiba2001@gmail.com",
                "rbarsha42@gmail.com",
                "sadasiba.domsgloballlp@gmail.com",
                "sadasiba.developer@domsglobal.co",
                "barsha.barik@domsglobal.co"
            ],
            "subject": "Important Notification TESTING - #1005",
            "message": "This is an important notification. Do not check",
            "html_message": "<h1>Important Notification</h1><p>This is an important notification.</p>"
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "Email sent successfully.")
        self.assertEqual(response.data["data"]["sent_count"], 5)
        self.assertEqual(response.data["data"]["total_recipients"], 5)

        # Check mail outbox
        self.assertEqual(len(mail.outbox), 1)
        sent_mail = mail.outbox[0]
        self.assertEqual(sent_mail.subject, "Important Notification TESTING - #1005")
        self.assertEqual(sent_mail.body, "This is an important notification. Do not check")
        self.assertEqual(len(sent_mail.bcc), 5)

    def test_send_email_endpoint_with_recipients_list(self):
        url = reverse('send-email')
        payload = {
            "recipients": [
                "sadasiba2001@gmail.com",
                "rbarsha42@gmail.com"
            ],
            "subject": "Testing Send Email Endpoint",
            "message": "Testing multi-recipient list on send endpoint.",
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["sent_count"], 2)

    def test_send_bulk_email_missing_fields(self):
        url = reverse('send-bulk-email')
        payload = {
            "recipients": ["user@example.com"],
            # Missing subject and message
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
