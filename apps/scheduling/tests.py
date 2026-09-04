from datetime import timedelta

from django.contrib.auth.models import User
from django.db import connection
from django.urls import reverse
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.scheduling.models import Appointment
from crm_api.models import Customer


class UpcomingAppointmentTests(TenantTestCase):
    """What the owner's dashboard panel is allowed to call 'Upcoming'."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@scheduling.test"
        tenant.name = "Scheduling Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        self.owner = User.objects.create_user(
            username="owner@scheduling.test", email="owner@scheduling.test",
            password="ownerpass123")
        token, _ = Token.objects.get_or_create(user=self.owner)
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION=f'Token {token.key}',
                             HTTP_X_TENANT_ID=self.tenant.schema_name)
        self.customer = Customer.objects.create(
            first_name="Meera", last_name="Nair", mobile_number="919845012345",
            customer_type="Women", garment_type="Saree")

        now = timezone.now()
        self.past = Appointment.objects.create(
            customer=self.customer, appointment_type='TRIAL',
            scheduled_time=now - timedelta(days=30))
        self.cancelled = Appointment.objects.create(
            customer=self.customer, appointment_type='MEASUREMENT',
            scheduled_time=now + timedelta(days=2), status='CANCELLED')
        self.soon = Appointment.objects.create(
            customer=self.customer, appointment_type='CONSULTATION',
            scheduled_time=now + timedelta(days=1))

    def ids(self, query=''):
        response = self.api.get(reverse('appointment-list') + query)
        self.assertEqual(response.status_code, 200, response.data)
        return [row['id'] for row in response.data]

    def test_upcoming_leaves_out_the_past_and_the_cancelled(self):
        rows = self.ids('?upcoming=true')
        self.assertEqual(rows, [str(self.soon.id)])

    def test_without_the_filter_the_whole_diary_is_still_there(self):
        # Cancellations and past fittings are the record; the panel just does
        # not lead with them.
        rows = self.ids()
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0], str(self.past.id), 'ordered by when, soonest first')

    def test_the_owner_sees_an_appointment_the_moment_it_is_booked(self):
        booked = self.api.post(reverse('appointment-list'), {
            'customer': str(self.customer.id),
            'appointment_type': 'TRIAL',
            'scheduled_time': (timezone.now() + timedelta(hours=3)).isoformat(),
        }, format='json')
        self.assertEqual(booked.status_code, 201, booked.data)
        self.assertIn(booked.data['id'], self.ids('?upcoming=true'))
