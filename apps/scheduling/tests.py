from datetime import timedelta
from django.contrib.auth.models import User
from django.db import connection
from django.urls import reverse
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.activities.models import UniversalActivity
from crm_api.models import Customer, Tailor
from .models import Appointment
from .repository import AppointmentRepository
from .serializers import AppointmentSerializer
from .services import AppointmentService


class SchedulingArchitectureTests(TenantTestCase):

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@scheduling.test"
        tenant.name = "Scheduling Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        self.user = User.objects.create_user(
            username="owner@scheduling.test",
            email="owner@scheduling.test",
            password="password123",
            first_name="Owner",
        )
        self.token, _ = Token.objects.get_or_create(user=self.user)
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {self.token.key}",
            HTTP_X_TENANT_ID=self.tenant.schema_name,
        )

        self.customer = Customer.objects.create(
            first_name="Ananya",
            last_name="Roy",
            mobile_number="9876543210",
        )
        self.tailor = Tailor.objects.create(
            name="Master Tailor",
            specialty="Embroidery",
        )
        self.scheduled_time = timezone.now() + timedelta(days=2)

    def test_create_appointment_api(self):
        url = reverse("appointment-list")
        payload = {
            "customer": str(self.customer.id),
            "appointment_type": "TRIAL",
            "scheduled_time": self.scheduled_time.isoformat(),
            "assigned_staff": self.tailor.id,
            "notes": "Bring dupatta for trial",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Appointment.objects.count(), 1)

        appointment = Appointment.objects.first()
        self.assertEqual(appointment.appointment_type, "TRIAL")
        self.assertEqual(appointment.notes, "Bring dupatta for trial")

        activity = UniversalActivity.objects.filter(
            module="scheduling", entity_id=str(appointment.id)
        ).first()
        self.assertIsNotNone(activity)
        self.assertEqual(activity.action, "SCHEDULED")

    def test_list_appointments_api(self):
        t1 = timezone.now() + timedelta(days=1)
        t2 = timezone.now() + timedelta(days=3)

        app2 = Appointment.objects.create(
            customer=self.customer, appointment_type="DELIVERY", scheduled_time=t2
        )
        app1 = Appointment.objects.create(
            customer=self.customer, appointment_type="TRIAL", scheduled_time=t1
        )

        url = reverse("appointment-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["id"], str(app1.id))
        self.assertEqual(data[1]["id"], str(app2.id))

    def test_retrieve_appointment_api(self):
        appointment = Appointment.objects.create(
            customer=self.customer,
            appointment_type="CONSULTATION",
            scheduled_time=self.scheduled_time,
        )
        url = reverse("appointment-detail", kwargs={"pk": appointment.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertEqual(data["id"], str(appointment.id))
        self.assertEqual(data["customer_detail"]["first_name"], "Ananya")

    def test_update_appointment_api(self):
        appointment = Appointment.objects.create(
            customer=self.customer,
            appointment_type="MEASUREMENT",
            scheduled_time=self.scheduled_time,
            status="SCHEDULED",
        )
        url = reverse("appointment-detail", kwargs={"pk": appointment.id})
        payload = {"status": "CONFIRMED", "notes": "Client confirmed attendance"}
        response = self.client.patch(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "CONFIRMED")
        self.assertEqual(appointment.notes, "Client confirmed attendance")

    def test_delete_appointment_api(self):
        appointment = Appointment.objects.create(
            customer=self.customer,
            appointment_type="TRIAL",
            scheduled_time=self.scheduled_time,
        )
        url = reverse("appointment-detail", kwargs={"pk": appointment.id})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Appointment.objects.count(), 0)

    def test_service_and_repository_direct_methods(self):
        app = Appointment.objects.create(
            customer=self.customer,
            appointment_type="TRIAL",
            scheduled_time=self.scheduled_time,
        )

        qs = AppointmentRepository.get_queryset_for_user(self.user)
        self.assertEqual(qs.count(), 1)

        fetched = AppointmentService.get_appointment_by_id(app.id, self.user)
        self.assertEqual(fetched.id, app.id)

        AppointmentService.delete_appointment(app)
        self.assertEqual(Appointment.objects.count(), 0)
