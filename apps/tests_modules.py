
from django.contrib.auth.models import User
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.activities.models import UniversalActivity
from apps.production.models import ProductionTask, QCRecord
from apps.scheduling.models import Appointment
from crm_api.models import Customer, Order, Tailor


class ModuleTestBase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@modules.test"
        tenant.name = "Modules Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        from django.db import connection
        connection.set_tenant(self.tenant)
        self.user = User.objects.create_user(
            username="owner@modules.test", email="owner@modules.test",
            password="pass12345", first_name="Owner",
        )
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION="Token " + Token.objects.create(user=self.user).key,
            HTTP_X_TENANT_ID=self.tenant.schema_name,
        )
        self.tailor = Tailor.objects.create(
            name="Anya", specialty="Lehenga", role="Tailor", status="Available")
        self.customer = Customer.objects.create(
            first_name="Meera", last_name="Nair", mobile_number="9700000001")
        self.order = Order.objects.create(
            order_id="T2B-MOD-0001", customer=self.customer, total_amount=10000)


class ProductionTaskTests(ModuleTestBase):
    def test_completing_a_task_stamps_completed_at(self):
        task = ProductionTask.objects.create(
            order=self.order, title="Cutting", stage_key="pattern_cutting",
            assigned_to=self.tailor, sequence=1,
        )
        response = self.client.patch(
            reverse("production-task-detail", args=[task.id]),
            {"status": "COMPLETED"}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        task.refresh_from_db()
        self.assertEqual(task.status, "COMPLETED")
        self.assertIsNotNone(task.completed_at)

    def test_task_update_writes_an_activity_entry(self):
        task = ProductionTask.objects.create(
            order=self.order, title="Finishing", stage_key="stitching_completed", sequence=2)
        self.client.patch(
            reverse("production-task-detail", args=[task.id]),
            {"status": "IN_PROGRESS"}, format="json",
        )
        entry = UniversalActivity.objects.filter(
            entity_type="ProductionTask", entity_id=str(task.id)).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.old_value["status"], "PENDING")
        self.assertEqual(entry.new_value["status"], "IN_PROGRESS")

    def test_rejects_an_unknown_status(self):
        task = ProductionTask.objects.create(
            order=self.order, title="Cutting", stage_key="pattern_cutting", sequence=1)
        response = self.client.patch(
            reverse("production-task-detail", args=[task.id]),
            {"status": "NOT_A_STATUS"}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_tasks_are_ordered_by_sequence(self):
        for seq, title in [(3, "Third"), (1, "First"), (2, "Second")]:
            ProductionTask.objects.create(
                order=self.order, title=title, stage_key="x", sequence=seq)
        titles = [t["title"] for t in self.client.get(reverse("production-task-list")).json()]
        self.assertEqual(titles, ["First", "Second", "Third"])


class QualityControlTests(ModuleTestBase):
    def test_recording_an_inspection_writes_an_activity_entry(self):
        response = self.client.post(reverse("qc-record-list"), {
            "order": self.order.id, "status": "PASSED",
            "comments": "Seams clean", "checklist_results": {"stitching_clean": True},
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(UniversalActivity.objects.filter(action="QC_SUBMITTED").exists())

    def test_rework_outcome_is_accepted(self):
        response = self.client.post(reverse("qc-record-list"), {
            "order": self.order.id, "status": "REWORK_REQUIRED", "comments": "Hem uneven",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(QCRecord.objects.get().status, "REWORK_REQUIRED")

    def test_rejects_an_unknown_outcome(self):
        response = self.client.post(reverse("qc-record-list"), {
            "order": self.order.id, "status": "MAYBE_FINE",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class AppointmentTests(ModuleTestBase):
    def test_booking_an_appointment(self):
        response = self.client.post(reverse("appointment-list"), {
            "customer": str(self.customer.id), "appointment_type": "TRIAL",
            "scheduled_time": "2026-09-01T10:30:00Z", "assigned_staff": self.tailor.id,
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Appointment.objects.get().appointment_type, "TRIAL")

    def test_scheduled_time_is_required(self):
        response = self.client.post(reverse("appointment-list"), {
            "customer": str(self.customer.id), "appointment_type": "TRIAL",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_an_unknown_appointment_type(self):
        response = self.client.post(reverse("appointment-list"), {
            "customer": str(self.customer.id), "appointment_type": "COFFEE",
            "scheduled_time": "2026-09-01T10:30:00Z",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_appointments_are_returned_in_time_order(self):
        for t in ["2026-09-03T10:00:00Z", "2026-09-01T10:00:00Z", "2026-09-02T10:00:00Z"]:
            Appointment.objects.create(
                customer=self.customer, appointment_type="TRIAL", scheduled_time=t)
        times = [a["scheduled_time"] for a in self.client.get(reverse("appointment-list")).json()]
        self.assertEqual(times, sorted(times))


class ActivityFeedTests(ModuleTestBase):
    def test_feed_is_newest_first(self):
        for i in range(3):
            UniversalActivity.objects.create(
                module="orders", entity_type="Order", entity_id=str(i),
                action="CREATED", title=f"Entry {i}",
            )
        titles = [a["title"] for a in self.client.get(reverse("universal-activity-list")).json()]
        self.assertEqual(titles, ["Entry 2", "Entry 1", "Entry 0"])

    def test_entry_keeps_the_actor_name_even_if_the_user_is_removed(self):
        entry = UniversalActivity.objects.create(
            user=self.user, user_name_snapshot="Owner", module="orders",
            entity_type="Order", entity_id="1", action="CREATED", title="Kept",
        )
        self.user.delete()
        entry.refresh_from_db()
        self.assertIsNone(entry.user)
        self.assertEqual(entry.user_name_snapshot, "Owner")
