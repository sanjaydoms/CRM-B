"""Tests for the production workflow engine.

OrderService.transition_order_stage is the most business-critical code in the
product -- it enforces who may advance a garment and in what order -- and had no
test coverage. These cases pin down the role gating, the sequencing guards, the
status mapping and the side effects on staff availability.
"""

from django.contrib.auth.models import User
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from crm_api.models import (
    BoutiqueSettings, Customer, Measurement, Order, OrderStage, Tailor,
)
from domains.orders.services import OrderService


class WorkflowTestBase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@workflow.test"
        tenant.name = "Workflow Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        from django.db import connection
        connection.set_tenant(self.tenant)

        self.owner = User.objects.create_user(
            username="owner@workflow.test", email="owner@workflow.test",
            password="ownerpass123", first_name="Owner",
        )
        self.master_user = User.objects.create_user(
            username="master@workflow.test", email="master@workflow.test",
            password="masterpass123", first_name="Rohit",
        )
        self.tailor_user = User.objects.create_user(
            username="tailor@workflow.test", email="tailor@workflow.test",
            password="tailorpass123", first_name="Anya",
        )
        self.master = Tailor.objects.create(
            name="Rohit Mehra", specialty="Bridal", role="Master",
            status="Available", user=self.master_user,
        )
        self.tailor = Tailor.objects.create(
            name="Anya Sharma", specialty="Lehenga", role="Tailor",
            status="Available", user=self.tailor_user,
        )
        BoutiqueSettings.objects.get_or_create(id=1)

    def make_customer(self, mobile="9800000001", with_measurements=True):
        customer = Customer.objects.create(
            first_name="Meera", last_name="Nair", mobile_number=mobile,
            garment_type="Lehenga",
        )
        if with_measurements:
            Measurement.objects.create(customer=customer, bust=36, waist=30, hips=38)
        return customer

    def make_order(self, customer=None, tailor=True, master=True, **kwargs):
        customer = customer or self.make_customer()
        data = {
            "base_price": 20000,
            "tailor_id": self.tailor.id if tailor else None,
            "master_id": self.master.id if master else None,
        }
        data.update(kwargs)
        return OrderService.create_order_for_customer(customer, data, user=self.owner)

    def stage(self, order, key):
        return order.stages.get(stage_key=key)

    def complete(self, order, key, user=None):
        return OrderService.transition_order_stage(
            order=order, stage_key=key, new_status="COMPLETED", user=user or self.owner,
        )


class RoleGatingTests(WorkflowTestBase):
    """Who is allowed to advance a stage."""

    def test_owner_can_advance_an_owner_master_stage(self):
        order = self.make_order()
        self.complete(order, "fabric_confirmed", user=self.owner)
        self.assertEqual(self.stage(order, "fabric_confirmed").status, "COMPLETED")

    def test_tailor_cannot_advance_a_master_only_stage(self):
        order = self.make_order()
        with self.assertRaises(ValueError) as ctx:
            OrderService.transition_order_stage(
                order=order, stage_key="pattern_cutting",
                new_status="COMPLETED", user=self.tailor_user,
            )
        self.assertIn("not authorized", str(ctx.exception).lower())

    def test_tailor_can_advance_a_tailor_stage(self):
        order = self.make_order()
        OrderService.transition_order_stage(
            order=order, stage_key="stitching_in_progress",
            new_status="IN_PROGRESS", user=self.tailor_user,
        )
        self.assertEqual(self.stage(order, "stitching_in_progress").status, "IN_PROGRESS")

    def test_master_can_run_quality_check(self):
        order = self.make_order()
        self.complete(order, "stitching_completed", user=self.tailor_user)
        OrderService.transition_order_stage(
            order=order, stage_key="master_quality_check",
            new_status="COMPLETED", user=self.master_user,
        )
        self.assertEqual(self.stage(order, "master_quality_check").status, "COMPLETED")

    def test_anonymous_caller_cannot_advance_a_stage(self):
        order = self.make_order()
        with self.assertRaises(ValueError):
            OrderService.transition_order_stage(
                order=order, stage_key="pattern_cutting",
                new_status="COMPLETED", user=None,
            )


class SequencingGuardTests(WorkflowTestBase):
    """A garment cannot skip ahead."""

    def test_cannot_deliver_before_quality_check(self):
        order = self.make_order()
        with self.assertRaises(ValueError) as ctx:
            self.complete(order, "delivered")
        self.assertIn("quality check", str(ctx.exception).lower())

    def test_can_deliver_once_quality_check_is_complete(self):
        order = self.make_order()
        self.complete(order, "stitching_completed")
        self.complete(order, "master_quality_check")
        self.complete(order, "delivered")
        self.assertEqual(self.stage(order, "delivered").status, "COMPLETED")

    def test_cannot_start_stitching_without_a_tailor(self):
        order = self.make_order(tailor=False)
        with self.assertRaises(ValueError) as ctx:
            OrderService.transition_order_stage(
                order=order, stage_key="stitching_in_progress",
                new_status="IN_PROGRESS", user=self.owner,
            )
        self.assertIn("tailor", str(ctx.exception).lower())

    def test_cannot_assign_tailor_without_measurements(self):
        customer = self.make_customer(mobile="9800000009", with_measurements=False)
        order = self.make_order(customer=customer)
        with self.assertRaises(ValueError) as ctx:
            self.complete(order, "assigned_to_tailor")
        self.assertIn("measurements", str(ctx.exception).lower())

    def test_cannot_schedule_trial_before_stitching_completes(self):
        order = self.make_order()
        with self.assertRaises(ValueError) as ctx:
            self.complete(order, "trial_scheduled")
        self.assertIn("stitching", str(ctx.exception).lower())

    def test_rejects_an_unknown_stage(self):
        order = self.make_order()
        with self.assertRaises(ValueError) as ctx:
            self.complete(order, "not_a_real_stage")
        self.assertIn("unknown stage", str(ctx.exception).lower())

    def test_rejects_an_invalid_status(self):
        order = self.make_order()
        with self.assertRaises(ValueError) as ctx:
            OrderService.transition_order_stage(
                order=order, stage_key="fabric_confirmed",
                new_status="FINISHED_I_GUESS", user=self.owner,
            )
        self.assertIn("invalid stage status", str(ctx.exception).lower())


class StageBookkeepingTests(WorkflowTestBase):
    """Timestamps, durations and derived order state."""

    def test_starting_a_stage_records_a_start_time(self):
        order = self.make_order()
        OrderService.transition_order_stage(
            order=order, stage_key="stitching_in_progress",
            new_status="IN_PROGRESS", user=self.tailor_user,
        )
        self.assertIsNotNone(self.stage(order, "stitching_in_progress").started_at)

    def test_completing_a_stage_records_duration(self):
        order = self.make_order()
        self.complete(order, "fabric_confirmed")
        stage = self.stage(order, "fabric_confirmed")
        self.assertIsNotNone(stage.completed_at)
        self.assertIsNotNone(stage.started_at)
        self.assertGreaterEqual(stage.duration_seconds, 0)

    def test_order_status_follows_the_stage(self):
        order = self.make_order()
        self.complete(order, "pattern_cutting")
        order.refresh_from_db()
        self.assertEqual(order.order_status, "Design & Creation")

    def test_quality_check_completion_moves_order_to_ready_for_dispatch(self):
        order = self.make_order()
        self.complete(order, "stitching_completed")
        self.complete(order, "master_quality_check")
        order.refresh_from_db()
        self.assertEqual(order.order_status, "Ready for Dispatch")

    def test_production_status_completes_only_when_every_stage_does(self):
        order = self.make_order()
        self.complete(order, "fabric_confirmed")
        order.refresh_from_db()
        self.assertEqual(order.production_status, "IN_PROGRESS")

        for conf in BoutiqueSettings.objects.get(id=1).workflow_config:
            stage = self.stage(order, conf["key"])
            if stage.status != "COMPLETED":
                stage.status = "COMPLETED"
                stage.save()
        self.complete(order, "delivered")
        order.refresh_from_db()
        self.assertEqual(order.production_status, "COMPLETED")

    def test_comments_are_recorded_against_the_stage(self):
        order = self.make_order()
        OrderService.transition_order_stage(
            order=order, stage_key="fabric_confirmed", new_status="COMPLETED",
            comments="Client approved the raw silk.", user=self.owner,
        )
        self.assertEqual(
            self.stage(order, "fabric_confirmed").comments,
            "Client approved the raw silk.",
        )


class StaffAvailabilityTests(WorkflowTestBase):
    def test_tailor_is_busy_while_stitching_and_free_afterwards(self):
        order = self.make_order()
        OrderService.transition_order_stage(
            order=order, stage_key="stitching_in_progress",
            new_status="IN_PROGRESS", user=self.tailor_user,
        )
        self.tailor.refresh_from_db()
        self.assertEqual(self.tailor.status, "Busy")

        self.complete(order, "stitching_completed", user=self.tailor_user)
        self.tailor.refresh_from_db()
        self.assertEqual(self.tailor.status, "Available")

    def test_master_is_freed_on_delivery(self):
        order = self.make_order()
        self.complete(order, "stitching_completed")
        self.complete(order, "master_quality_check")
        self.complete(order, "delivered")
        self.master.refresh_from_db()
        self.assertEqual(self.master.status, "Available")


class OrderCreationTests(WorkflowTestBase):
    def test_order_is_created_with_its_full_stage_list(self):
        order = self.make_order()
        expected = len(BoutiqueSettings.objects.get(id=1).workflow_config)
        self.assertEqual(order.stages.count(), expected)

    def test_measurements_stage_is_pre_completed_when_sizing_exists(self):
        order = self.make_order()
        self.assertEqual(self.stage(order, "measurements_completed").status, "COMPLETED")

    def test_measurements_stage_is_open_when_sizing_is_missing(self):
        customer = self.make_customer(mobile="9800000021", with_measurements=False)
        order = self.make_order(customer=customer)
        self.assertEqual(self.stage(order, "measurements_completed").status, "NOT_STARTED")

    def test_production_tasks_are_created_and_routed(self):
        from apps.production.models import ProductionTask
        order = self.make_order()
        tasks = ProductionTask.objects.filter(order=order)
        self.assertEqual(tasks.count(), 8)
        stitching = tasks.get(stage_key="stitching_in_progress")
        self.assertEqual(stitching.assigned_to, self.tailor)
        cutting = tasks.get(stage_key="pattern_cutting")
        self.assertEqual(cutting.assigned_to, self.master)

    def test_order_ids_are_unique_across_many_orders(self):
        ids = set()
        for i in range(25):
            customer = self.make_customer(mobile=f"97000000{i:02d}")
            ids.add(self.make_order(customer=customer).order_id)
        self.assertEqual(len(ids), 25, "order_id collision")

    def test_pricing_applies_five_percent_tax(self):
        customer = self.make_customer(mobile="9800000031")
        order = OrderService.create_order_for_customer(
            customer,
            {"base_price": 1000, "fabric_price": 500, "embroidery_price": 200,
             "customization_price": 100, "tailoring_charges": 100, "packaging_handling": 100},
            user=self.owner,
        )
        self.assertEqual(float(order.taxes), 100.0)
        self.assertEqual(float(order.total_amount), 2100.0)

    def test_malformed_prices_do_not_crash_order_creation(self):
        customer = self.make_customer(mobile="9800000032")
        order = OrderService.create_order_for_customer(
            customer,
            {"base_price": "not-a-number", "fabric_price": None, "embroidery_price": ""},
            user=self.owner,
        )
        self.assertEqual(float(order.total_amount), 0.0)

    def test_partial_payment_records_the_advance(self):
        customer = self.make_customer(mobile="9800000033")
        order = OrderService.create_order_for_customer(
            customer,
            {"base_price": 10000, "payment_status": "Partially Paid", "advance_paid": 4000},
            user=self.owner,
        )
        self.assertEqual(float(order.advance_paid), 4000.0)
        self.assertEqual(float(order.amount_paid), 4000.0)

    def test_failed_order_creation_leaves_nothing_behind(self):
        """Order creation is atomic -- a failure must not leave partial rows."""
        from unittest.mock import patch
        customer = self.make_customer(mobile="9800000034")
        before = Order.objects.count()
        with patch("apps.production.models.ProductionTask.objects.bulk_create",
                   side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.make_order(customer=customer)
        self.assertEqual(Order.objects.count(), before)
        self.assertEqual(OrderStage.objects.filter(order__customer=customer).count(), 0)


class MasterJourneyTests(WorkflowTestBase):
    """The full path a supervising master walks, as the API sees it."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION="Token " + Token.objects.create(user=self.master_user).key,
            HTTP_X_TENANT_ID=self.tenant.schema_name,
        )

    def _transition(self, order, stage_key, new_status="COMPLETED"):
        return self.client.post(
            reverse("order-transition-stage", args=[order.id]),
            {"stage_key": stage_key, "status": new_status}, format="multipart",
        )

    def test_master_sees_the_orders_they_supervise(self):
        mine = self.make_order()
        other_master = Tailor.objects.create(name="Other", specialty="X", role="Master")
        theirs = self.make_order(
            customer=self.make_customer(mobile="9811111111"), master=False)
        theirs.master = other_master
        theirs.save()

        body = self.client.get(reverse("order-list")).json()
        supervised = [o for o in body if o["master"] == self.master.id]
        self.assertIn(mine.order_id, [o["order_id"] for o in supervised])

    def test_master_walks_an_order_from_cutting_to_delivered(self):
        order = self.make_order()

        # Stages the master owns.
        self.assertEqual(self._transition(order, "fabric_confirmed").status_code, 200)
        self.assertEqual(self._transition(order, "pattern_cutting").status_code, 200)
        self.assertEqual(self._transition(order, "assigned_to_tailor").status_code, 200)

        # Stitching belongs to the tailor -- the master is refused, with a reason.
        blocked = self._transition(order, "stitching_in_progress", "IN_PROGRESS")
        self.assertEqual(blocked.status_code, 400)
        self.assertIn("not authorized", blocked.json()["error"].lower())

        # Delivery is refused until the master's own quality check is done.
        early = self._transition(order, "delivered")
        self.assertEqual(early.status_code, 400)
        self.assertIn("quality check", early.json()["error"].lower())

        # The tailor does their part.
        for stage_key in ["stitching_in_progress", "stitching_completed"]:
            OrderService.transition_order_stage(
                order=order, stage_key=stage_key,
                new_status="COMPLETED", user=self.tailor_user,
            )
        for stage_key in ["master_quality_check", "trial_scheduled", "trial_completed",
                          "ready_for_delivery", "delivered"]:
            self.assertEqual(self._transition(order, stage_key).status_code, 200, stage_key)

        order.refresh_from_db()
        self.assertEqual(order.order_status, "Delivered")
        self.assertEqual(order.stages.filter(status="COMPLETED").count(), 12)

    def test_master_work_is_attributed_to_them(self):
        order = self.make_order()
        self._transition(order, "pattern_cutting")
        self.assertEqual(self.stage(order, "pattern_cutting").performed_by, self.master)

    def test_completing_delivery_frees_the_master(self):
        order = self.make_order()
        self.master.status = "Busy"
        self.master.save()
        OrderService.transition_order_stage(
            order=order, stage_key="stitching_completed",
            new_status="COMPLETED", user=self.tailor_user,
        )
        self._transition(order, "master_quality_check")
        self._transition(order, "delivered")
        self.master.refresh_from_db()
        self.assertEqual(self.master.status, "Available")

    def test_master_cannot_mark_delivered_through_the_status_shortcut(self):
        """The assignments screen exposes a status dropdown; it must obey the
        same guards as the stage tracker."""
        order = self.make_order()
        response = self.client.patch(
            reverse("order-update-status", args=[order.id]),
            {"status": "Delivered"}, format="json",
        )
        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertNotEqual(order.order_status, "Delivered")


class TransitionEndpointTests(WorkflowTestBase):
    """The HTTP surface around the workflow engine."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.token = Token.objects.create(user=self.owner)
        self.client.credentials(
            HTTP_AUTHORIZATION="Token " + self.token.key,
            HTTP_X_TENANT_ID=self.tenant.schema_name,
        )

    def test_transition_requires_stage_key_and_status(self):
        order = self.make_order()
        url = reverse("order-transition-stage", args=[order.id])
        response = self.client.post(url, {"stage_key": "fabric_confirmed"}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_guard_violation_returns_400_not_500(self):
        order = self.make_order()
        url = reverse("order-transition-stage", args=[order.id])
        response = self.client.post(
            url, {"stage_key": "delivered", "status": "COMPLETED"}, format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("quality check", response.json()["error"].lower())

    def test_update_status_cannot_skip_the_quality_check(self):
        """The status dropdown used to bypass every guard.

        A master could mark a garment Delivered while the quality check had
        never started -- the client was told it shipped, the production record
        showed nothing done.
        """
        order = self.make_order()
        response = self.client.patch(
            reverse("order-update-status", args=[order.id]),
            {"status": "Delivered"}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        order.refresh_from_db()
        self.assertNotEqual(order.order_status, "Delivered")
        self.assertEqual(self.stage(order, "delivered").status, "NOT_STARTED")

    def test_update_status_advances_the_matching_stage(self):
        order = self.make_order()
        response = self.client.patch(
            reverse("order-update-status", args=[order.id]),
            {"status": "Confirmed"}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.stage(order, "fabric_confirmed").status, "COMPLETED")

    def test_update_status_in_the_right_order_reaches_delivered(self):
        order = self.make_order()
        for target in ["Quality Check", "Ready for Dispatch", "Delivered"]:
            if target == "Delivered":
                # Quality check is a stage of its own, not a client-facing status.
                self.complete(order, "master_quality_check")
            response = self.client.patch(
                reverse("order-update-status", args=[order.id]),
                {"status": target}, format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK, target)
        order.refresh_from_db()
        self.assertEqual(order.order_status, "Delivered")
        self.assertEqual(self.stage(order, "delivered").status, "COMPLETED")

    def test_tailor_cannot_use_update_status_to_reach_a_master_stage(self):
        order = self.make_order()
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION="Token " + Token.objects.create(user=self.tailor_user).key,
            HTTP_X_TENANT_ID=self.tenant.schema_name,
        )
        response = client.patch(
            reverse("order-update-status", args=[order.id]),
            {"status": "Ready for Dispatch"}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_status_without_a_stage_is_recorded_as_is(self):
        order = self.make_order()
        response = self.client.patch(
            reverse("order-update-status", args=[order.id]),
            {"status": "Stylist Review"}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.order_status, "Stylist Review")

    def test_successful_transition_returns_the_updated_order(self):
        order = self.make_order()
        url = reverse("order-transition-stage", args=[order.id])
        response = self.client.post(
            url, {"stage_key": "fabric_confirmed", "status": "COMPLETED"}, format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        completed = [s for s in body["stages"] if s["stage_key"] == "fabric_confirmed"]
        self.assertEqual(completed[0]["status"], "COMPLETED")
