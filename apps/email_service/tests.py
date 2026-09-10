"""The outbound mailer over HTTP, and who is allowed to reach it.

/api/email/ is governed by the `email` module (core/modules.py), so every test
here signs in as somebody the gate actually admits. That is not a workaround
for the gate -- it is the point of it. These four views let any signed-in
caller send arbitrary subject and body, in bulk, from the boutique's own
sender address, and until the module was registered they answered for every
boutique and every role.

WHY A TENANT ROLE MAP CAN GOVERN A SHARED_APPS ROUTE. apps.email_service is in
SHARED_APPS, which decides where its MODELS live -- it has none, and its jobs
live in Redis, one queue for the platform. It does NOT decide where the route
is mounted or who reaches it: boutique_crm/urls.py mounts /api/email/ in the
same urlconf as everything else, and TenantHeaderMiddleware 400s any /api/
path that arrives without a tenant. So a request that reaches these views is
always inside a tenant schema, BoutiqueSettings.role_modules is always
readable, and Layer 2 governs this prefix exactly as it governs a tenant app's.
test_the_owner_can_grant_email_to_a_role proves that rather than asserting it.

Nothing internal is affected by the gate: password reset (crm_api/auth_views.py)
and order mail (domains/orders/emails.py) call EmailService directly and never
cross this HTTP surface.
"""

from django.contrib.auth.models import User
from django.core import mail
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

OWNER_EMAIL = "testowner@example.com"


class MultiRecipientEmailAPITest(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = OWNER_EMAIL
        tenant.name = "Test Boutique"
        return tenant

    def setUp(self):
        super().setUp()
        from django.db import connection
        connection.set_tenant(self.tenant)

        # The caller is the boutique OWNER, by the address on the registry row.
        # It used to be an unrelated `user@example.com`, which core.roles now
        # resolves to no role at all (a missing profile is not proof of
        # ownership -- see core/roles.py), and no role means no `email`:
        # ROLE_DEFAULTS grants this module to nobody, so outbound mail starts
        # as the owner's alone and is handed out from Boutique Settings.
        self.user = User.objects.create_user(
            username="emailtestowner", email=OWNER_EMAIL, password="password123"
        )
        self.token = Token.objects.create(user=self.user)
        self.client = self._client_for(self.token)

    def _client_for(self, token):
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f'Token {token.key}',
            HTTP_X_TENANT_ID=self.tenant.schema_name,
        )
        return client

    def _tailor_client(self, email="tailor@example.com"):
        from crm_api.models import Tailor

        user = User.objects.create_user(
            username=email, email=email, password="password123")
        Tailor.objects.create(
            user=user, name=email, specialty='Blouse', role='Tailor')
        return self._client_for(Token.objects.create(user=user))

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
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_a_tailor_is_refused_and_nothing_leaves_the_building(self):
        """The gate, stated as a test so it cannot be "fixed" by removing it.

        A 400 here would mean the request reached field validation, i.e. past
        the permission layer. The message has to name the module: a bare
        "Forbidden" on a send endpoint is indistinguishable from a broken SMTP
        configuration, and the two get debugged in completely different places.
        """
        response = self._tailor_client().post(
            reverse('send-bulk-email'),
            {"recipients": ["someone@example.com"], "subject": "x", "message": "y"},
            format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('Email', response.data['detail'])
        self.assertIn('Tailor', response.data['detail'])
        self.assertEqual(mail.outbox, [])

    def test_the_owner_can_grant_email_to_a_role(self):
        """Layer 2 governs this prefix, even though the app is in SHARED_APPS.

        BoutiqueSettings lives in the TENANT schema. If the middleware ever let
        a request reach these views without one -- the thing SHARED_APPS might
        plausibly imply -- this test would 403 after the grant, or 500 looking
        for the table.
        """
        from crm_api.models import BoutiqueSettings

        client = self._tailor_client('grantable@example.com')
        payload = {"recipients": ["someone@example.com"],
                   "subject": "x", "message": "y"}
        url = reverse('send-bulk-email')

        self.assertEqual(client.post(url, payload, format='json').status_code,
                         status.HTTP_403_FORBIDDEN)

        BoutiqueSettings.objects.update_or_create(
            id=1, defaults={'role_modules': {'Tailor': {'email': True}}})

        self.assertEqual(client.post(url, payload, format='json').status_code,
                         status.HTTP_200_OK)
