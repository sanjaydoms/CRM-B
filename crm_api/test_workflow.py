"""Tests for the production workflow engine.

OrderService.transition_order_stage is the most business-critical code in the
product -- it enforces who may advance a garment and in what order -- and had no
test coverage. These cases pin down the role gating, the sequencing guards, the
status mapping and the side effects on staff availability.
"""

import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from crm_api.models import (
    BoutiqueSettings, Customer, Measurement, Notification, Order, OrderStage, Tailor,
)
from domains.orders.repositories import OrderRepository
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

    def test_production_status_completes_on_an_order_loaded_the_way_the_api_loads_it(self):
        """The test above passes an order built in memory, whose `stages` was
        never prefetched. Every real transition arrives through OrderViewSet,
        which loads orders from OrderRepository.base_queryset() -- and that
        prefetches 'stages'. Reading order.stages.all() then returned the
        prefetch cache from before the stage was saved, so the "all done" test
        was always one transition stale and production_status stayed
        IN_PROGRESS even on a delivered order.
        """
        order = self.make_order()
        for conf in BoutiqueSettings.objects.get(id=1).workflow_config:
            stage = self.stage(order, conf["key"])
            if stage.status != "COMPLETED" and conf["key"] != "delivered":
                stage.status = "COMPLETED"
                stage.save()

        # The prefetch is the whole point -- do not swap this for Order.objects.get.
        prefetched = OrderRepository.get_by_id(order.id)
        self.complete(prefetched, "delivered")

        order.refresh_from_db()
        self.assertEqual(order.production_status, "COMPLETED")

    def test_a_skipped_stage_does_not_strand_production_status(self):
        """Skip Stage is a real button in the owner's stage modal, and the
        ladder lets an order deliver over a skipped stage. Treating SKIPPED as
        outstanding work would leave every such order reading IN_PROGRESS
        forever.
        """
        order = self.make_order()
        for conf in BoutiqueSettings.objects.get(id=1).workflow_config:
            key = conf["key"]
            if key == "delivered":
                continue
            stage = self.stage(order, key)
            stage.status = "SKIPPED" if key == "maggam_work" else "COMPLETED"
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

    def test_the_promised_delivery_date_is_the_one_that_is_kept(self):
        """The date the boutique quoted per garment is what the tracking page
        and the WhatsApp update show the customer. It used to be discarded in
        favour of today+15, so a September garment was promised in August.
        """
        order = self.make_order(estimated_delivery="2026-09-15")
        order.refresh_from_db()
        self.assertEqual(str(order.estimated_delivery), "2026-09-15")

    def test_delivery_estimate_falls_back_when_no_date_was_promised(self):
        order = self.make_order()
        expected = datetime.date.today() + datetime.timedelta(days=15)
        self.assertEqual(order.estimated_delivery, expected)

    def test_a_malformed_delivery_date_does_not_take_the_order_down(self):
        """The date arrives as text from the browser. Notifications format it
        during creation, so an unparseable value must not reach the order --
        it fails there with AttributeError and the customer gets no order.
        """
        order = self.make_order(estimated_delivery="not-a-date")
        expected = datetime.date.today() + datetime.timedelta(days=15)
        self.assertEqual(order.estimated_delivery, expected)

    def test_the_order_carries_the_identity_its_invoice_has_to_print(self):
        """The invoice is printed from the Invoices tab, where none of the
        order wizard's state exists. It used to fall back to that state and
        bill whichever customer the wizard last held -- the wrong person, and
        one client's contact details shown on another's invoice. The order
        payload has to carry its own customer's identity for that to be fixable.
        """
        from crm_api.serializers import OrderSerializer

        customer = self.make_customer(mobile="9800000077")
        customer.email_address = "meera@example.test"
        customer.address = "12 Kamaraj Street, Chennai"
        customer.save()
        order = self.make_order(customer=customer)

        data = OrderSerializer(order).data

        self.assertEqual(data["customer_name"], "Meera Nair")
        self.assertEqual(data["customer_mobile"], "9800000077")
        self.assertEqual(data["customer_email"], "meera@example.test")
        self.assertEqual(data["customer_address"], "12 Kamaraj Street, Chennai")

    def test_production_tasks_are_created_and_routed(self):
        from apps.production.models import ProductionTask
        order = self.make_order()
        tasks = ProductionTask.objects.filter(order=order)
        self.assertEqual(tasks.count(), 9)
        stitching = tasks.get(stage_key="stitching_in_progress")
        self.assertEqual(stitching.assigned_to, self.tailor)
        cutting = tasks.get(stage_key="pattern_cutting")
        self.assertEqual(cutting.assigned_to, self.master)
        # Finishing and pressing became stages of their own, so each has its own task.
        self.assertTrue(tasks.filter(stage_key="finishing").exists())
        self.assertTrue(tasks.filter(stage_key="pressing").exists())
        # Every task must point at a stage that actually exists on the order.
        stage_keys = set(order.stages.values_list("stage_key", flat=True))
        orphans = set(tasks.values_list("stage_key", flat=True)) - stage_keys
        self.assertEqual(orphans, set(), f"tasks reference non-existent stages: {orphans}")

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
        """The dropdown walks the client-facing statuses in order, and that is
        now enough on its own -- 'Design & Creation' records that the stitching
        is finished, so quality check has something to inspect. This case used
        to open on 'Quality Check' and complete master_quality_check by hand,
        because no dropdown value touched either stitching stage.
        """
        order = self.make_order()
        for target in ["Confirmed", "Design & Creation", "Quality Check",
                       "Ready for Dispatch", "Delivered"]:
            response = self.client.patch(
                reverse("order-update-status", args=[order.id]),
                {"status": target}, format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK,
                             f"{target} -> {response.data}")
        order.refresh_from_db()
        self.assertEqual(order.order_status, "Delivered")
        self.assertEqual(self.stage(order, "delivered").status, "COMPLETED")
        # And the garment is recorded as actually made.
        self.assertEqual(self.stage(order, "stitching_completed").status, "COMPLETED")

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


class DashboardAndNotificationScopingTests(WorkflowTestBase):
    """What a signed-in tailor is allowed to read.

    OrderViewSet already hid other people's orders behind visible_orders, but
    two endpoints routed around it: the dashboard read Order.objects and
    Customer.objects directly, and the notification list trusted a
    client-supplied ?role=. Between them a tailor could read the boutique's
    turnover and every client's contact details and unpaid balance.
    """

    def _client_for(self, user):
        client = APIClient()
        token, _ = Token.objects.get_or_create(user=user)
        client.credentials(
            HTTP_AUTHORIZATION="Token " + token.key,
            HTTP_X_TENANT_ID=self.tenant.schema_name,
        )
        return client

    def setUp(self):
        super().setUp()
        # One order the tailor is on, one they are not.
        self.theirs = self.make_order()
        stranger = self.make_customer(mobile="9800000099")
        self.not_theirs = self.make_order(customer=stranger, tailor=False, master=False)

    def test_the_dashboard_does_not_hand_a_tailor_the_whole_boutique(self):
        response = self._client_for(self.tailor_user).get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        stats = response.data["stats"]
        self.assertEqual(stats["total_orders"], 1)
        self.assertEqual(stats["total_customers"], 1)
        names = [c["first_name"] for c in response.data["recent_customers"]]
        self.assertNotIn("Meera", names[1:2])
        self.assertEqual(len(response.data["recent_orders"]), 1)

    def test_the_owner_still_sees_everything_on_the_dashboard(self):
        response = self._client_for(self.owner).get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["stats"]["total_orders"], 2)
        self.assertEqual(response.data["stats"]["total_customers"], 2)

    def test_a_tailor_cannot_ask_for_the_owners_notifications(self):
        Notification.objects.create(
            recipient_role="Owner", recipient_email="owner@workflow.test",
            title="Turnover", message="Balance of Rs20000 outstanding.",
        )

        response = self._client_for(self.tailor_user).get(
            "/api/notifications/", {"role": "Owner"})

        self.assertEqual(response.status_code, 200)
        # The param is ignored now, so the tailor gets their own rows (order
        # creation already raised one). What must not appear is anyone else's.
        self.assertEqual({n["recipient_role"] for n in response.data} - {"Tailor"}, set())

    def test_an_unrecognised_role_returns_nothing_rather_than_everything(self):
        Notification.objects.create(
            recipient_role="Customer", recipient_email="meera@example.test",
            title="Delivered", message="Please complete your remaining balance.",
        )

        response = self._client_for(self.tailor_user).get(
            "/api/notifications/", {"role": "Customer"})

        self.assertEqual(response.status_code, 200)
        roles = {n["recipient_role"] for n in response.data}
        self.assertNotIn("Customer", roles)
        messages = " ".join(n["message"] for n in response.data)
        self.assertNotIn("remaining balance", messages)

    def test_a_tailor_still_receives_their_own_notifications(self):
        Notification.objects.create(
            recipient_role="Tailor", recipient_email="tailor@workflow.test",
            title="Assigned", message="You have been assigned an order.",
        )

        response = self._client_for(self.tailor_user).get("/api/notifications/")

        self.assertEqual(response.status_code, 200)
        titles = [n["title"] for n in response.data]
        self.assertIn("Assigned", titles)
        self.assertEqual({n["recipient_role"] for n in response.data}, {"Tailor"})


class StatusDropdownTests(WorkflowTestBase):
    """The Update Status dropdown, which is a second way to drive the ladder.

    It has to mean the same thing as the stage tracker beside it, and it has to
    be able to express every status it offers.
    """

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        token, _ = Token.objects.get_or_create(user=self.owner)
        self.client.credentials(
            HTTP_AUTHORIZATION="Token " + token.key,
            HTTP_X_TENANT_ID=self.tenant.schema_name,
        )

    def _set(self, order, value):
        return self.client.patch(
            reverse("order-update-status", args=[order.id]),
            {"status": value}, format="json")

    def test_shipped_is_actually_stored(self):
        """'Shipped' used to alias the ready_for_delivery stage, whose own map
        turns it back into 'Ready for Dispatch' -- so the endpoint answered 200
        for a status it never stored, and the only customer message carrying
        the courier name and tracking number could never fire.
        """
        order = self.make_order(
            delivery_method="Courier", courier_service="BlueDart",
            tracking_number="BD123456789")
        self.complete(order, "stitching_completed")
        self.complete(order, "master_quality_check")

        response = self._set(order, "Shipped")

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.order_status, "Shipped")

    def test_choosing_quality_check_actually_runs_quality_check(self):
        """It used to complete stitching_completed while delivery is gated on
        master_quality_check, so the dropdown claimed QC had happened and then
        refused the final rung naming a step it had never offered.
        """
        order = self.make_order()
        self._set(order, "Design & Creation")

        response = self._set(order, "Quality Check")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.stage(order, "master_quality_check").status, "COMPLETED")

    def test_the_dropdown_can_walk_an_order_all_the_way_to_delivered(self):
        """The whole point of the control. Before, the last hop returned 400."""
        order = self.make_order()
        for value in ["Confirmed", "Design & Creation", "Quality Check",
                      "Ready for Dispatch", "Delivered"]:
            response = self._set(order, value)
            self.assertEqual(response.status_code, 200, f"{value} -> {response.data}")

        order.refresh_from_db()
        self.assertEqual(order.order_status, "Delivered")

    def test_a_refused_transition_explains_itself(self):
        """The reason has to survive as far as the owner; api.js prints it."""
        order = self.make_order()

        response = self._set(order, "Delivered")

        self.assertEqual(response.status_code, 400)
        self.assertIn("quality check", str(response.data).lower())


class OrderMoneyTests(WorkflowTestBase):
    """Money at the two points it can be wrong: creation, and afterwards."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        token, _ = Token.objects.get_or_create(user=self.owner)
        self.client.credentials(
            HTTP_AUTHORIZATION="Token " + token.key,
            HTTP_X_TENANT_ID=self.tenant.schema_name,
        )

    def _create(self, customer, **data):
        return self.client.post(
            reverse("customer-create-order", args=[customer.id]), data, format="json")

    def test_an_advance_larger_than_the_order_is_clamped_not_banked(self):
        """150000 against a 31500 order used to be stored verbatim and counted
        as revenue, while the customer's page read 'Balance due Rs0.00'.
        """
        order = self.make_order(
            base_price=30000, payment_status="Partially Paid", advance_paid=150000)

        self.assertEqual(order.amount_paid, order.total_amount)
        self.assertLessEqual(order.advance_paid, order.total_amount)

    def test_a_negative_advance_is_floored_at_zero(self):
        order = self.make_order(
            base_price=30000, payment_status="Partially Paid", advance_paid=-5000)

        self.assertGreaterEqual(order.advance_paid, 0)

    def test_a_negative_price_is_refused_rather_than_banked(self):
        """A negative base price took the dashboard's revenue below zero."""
        customer = self.make_customer(mobile="9800000031")

        response = self._create(customer, base_price=-32000)

        self.assertEqual(response.status_code, 400)
        self.assertIn("negative", str(response.data).lower())

    def test_an_impossible_total_is_refused_with_a_readable_reason(self):
        """total_amount is max_digits=10; 10^8 up died as an unhandled
        psycopg DataError behind a generic 'Failed to submit order'.
        """
        customer = self.make_customer(mobile="9800000032")

        response = self._create(customer, base_price=99999999)

        self.assertEqual(response.status_code, 400)
        self.assertIn("maximum", str(response.data).lower())

    def test_a_part_payment_can_be_recorded_after_the_order_exists(self):
        """There was no way to do this at all: the status dropdown was the only
        control and 'Partially Paid' was a silent no-op.
        """
        order = self.make_order(base_price=30000, payment_status="Pending")
        url = reverse("order-detail", args=[order.id])

        response = self.client.patch(url, {"amount_paid": "10000.00"}, format="json")

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.amount_paid, Decimal("10000.00"))
        self.assertEqual(order.payment_status, "Partially Paid")

    def test_paying_the_balance_settles_the_order(self):
        order = self.make_order(base_price=30000, payment_status="Pending")
        url = reverse("order-detail", args=[order.id])

        self.client.patch(url, {"amount_paid": str(order.total_amount)}, format="json")

        order.refresh_from_db()
        self.assertEqual(order.payment_status, "Paid")

    def test_marking_pending_does_not_leave_a_stale_advance_behind(self):
        """The invoice printed 'Advance Paid Rs10,000 / Balance Due Rs0' beside
        a table saying the full amount was outstanding.
        """
        order = self.make_order(
            base_price=30000, payment_status="Partially Paid", advance_paid=10000)
        url = reverse("order-detail", args=[order.id])

        self.client.patch(url, {"payment_status": "Pending"}, format="json")

        order.refresh_from_db()
        self.assertEqual(order.amount_paid, Decimal("0.00"))
        self.assertEqual(order.advance_paid, Decimal("0.00"))


class StaffAvailabilityAcrossOrdersTests(WorkflowTestBase):
    """Availability has to account for every order a person is on, not just
    the one whose stage was touched."""

    def test_finishing_one_garment_does_not_free_a_tailor_who_has_another(self):
        """Tailor.status is one flag with no reference counting: completing
        stitching on any ONE order used to write 'Available' outright, so a
        tailor with three garments open advertised as free after the first.
        """
        first = self.make_order()
        second = self.make_order(customer=self.make_customer(mobile="9800000041"))

        self.complete(first, "stitching_completed", user=self.tailor_user)

        self.tailor.refresh_from_db()
        self.assertEqual(self.tailor.status, "Busy")

    def test_the_tailor_frees_up_once_the_last_garment_is_stitched(self):
        first = self.make_order()
        second = self.make_order(customer=self.make_customer(mobile="9800000042"))

        self.complete(first, "stitching_completed", user=self.tailor_user)
        self.complete(second, "stitching_completed", user=self.tailor_user)

        self.tailor.refresh_from_db()
        self.assertEqual(self.tailor.status, "Available")


class BackendCorrectnessTests(WorkflowTestBase):
    """Defects found by the end-to-end audit, each pinned to its symptom."""

    def test_a_stage_can_be_paused(self):
        """The stage modal has a 'Pause Stage' button, the model documents
        PAUSED and the dashboard has a colour for it -- but the service
        rejected the value, so all of that was dead code.
        """
        order = self.make_order()
        OrderService.transition_order_stage(
            order=order, stage_key="fabric_confirmed",
            new_status="PAUSED", user=self.owner,
        )
        self.assertEqual(self.stage(order, "fabric_confirmed").status, "PAUSED")

    def test_special_instructions_survive_order_creation(self):
        """The last wizard step asks for them and posted them as
        custom_requirements; nothing read the key and Order had no field, so
        an instruction the staff were asked for was silently dropped.
        """
        order = self.make_order(custom_requirements="Extra margin at the waist.")
        order.refresh_from_db()
        self.assertEqual(order.special_instructions, "Extra margin at the waist.")

    def test_the_production_task_follows_its_stage(self):
        """Nine tasks are written per order and nothing ever touched them, so
        the production endpoints reported every task NOT_STARTED on a
        delivered order.
        """
        from apps.production.models import ProductionTask

        order = self.make_order()
        self.complete(order, "fabric_confirmed")

        task = ProductionTask.objects.get(order=order, stage_key="fabric_confirmed")
        self.assertEqual(task.status, "COMPLETED")

    def test_every_production_task_has_someone_on_it_without_a_master(self):
        """Three of the nine were assigned to master with no `or tailor`
        fallback, unlike their six siblings -- and master is optional in the
        wizard, so those three were created unassigned.
        """
        from apps.production.models import ProductionTask

        order = self.make_order(master=False)

        unassigned = ProductionTask.objects.filter(order=order, assigned_to__isnull=True)
        self.assertEqual(list(unassigned), [])

    def test_ready_for_dispatch_does_not_claim_a_quality_check_that_never_ran(self):
        """'Ready for Dispatch' is reached from three stages, none of which
        require master_quality_check, and the message asserted the garment had
        passed inspection regardless.
        """
        order = self.make_order()
        self.complete(order, "stitching_completed")
        self.complete(order, "trial_scheduled")

        messages = " ".join(
            n.message for n in Notification.objects.filter(recipient_role="Customer"))
        self.assertNotIn("passed quality checks", messages)


class CustomerContactValidationTests(WorkflowTestBase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        token, _ = Token.objects.get_or_create(user=self.owner)
        self.client.credentials(
            HTTP_AUTHORIZATION="Token " + token.key,
            HTTP_X_TENANT_ID=self.tenant.schema_name,
        )

    def test_an_unreachable_mobile_number_is_refused(self):
        """No validator on the model, none in the serializer, none on the form:
        a nine-digit slip was stored and every WhatsApp update after it opened a
        chat with nobody, behind a button the owner could mark as sent.
        """
        response = self.client.post('/api/customers/', {
            'first_name': 'Meera', 'last_name': 'Iyer',
            'mobile_number': '96001',
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('mobile_number', response.data)

    def test_a_good_mobile_number_is_accepted(self):
        response = self.client.post('/api/customers/', {
            'first_name': 'Meera', 'last_name': 'Iyer',
            'mobile_number': '9600123456',
        }, format='json')

        self.assertEqual(response.status_code, 201, response.data)


class FabricSelectionTests(WorkflowTestBase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        token, _ = Token.objects.get_or_create(user=self.owner)
        self.client.credentials(
            HTTP_AUTHORIZATION="Token " + token.key,
            HTTP_X_TENANT_ID=self.tenant.schema_name,
        )

    def test_changing_the_fabric_replaces_the_pick_instead_of_stacking_rows(self):
        """'Save as Draft' and 'Next' both post here, and Back/Next through
        step 4 posts again, so a customer who changed their mind twice ended up
        with three selections and no route to delete any of them -- while the
        design studio's context builder reads whatever rows exist.
        """
        customer = self.make_customer(mobile="9800000051")
        url = f'/api/customers/{customer.id}/fabric-selections/'

        self.client.post(url, {'fabric_name': 'Raw Silk', 'fabric_price': '1850'}, format='multipart')
        self.client.post(url, {'fabric_name': 'Banarasi', 'fabric_price': '2850'}, format='multipart')

        self.assertEqual(customer.fabric_selections.count(), 1)
        self.assertEqual(customer.fabric_selections.first().fabric_name, 'Banarasi')


class MasterJourneyTests(WorkflowTestBase):
    """The supervisor's path. A Master runs the floor but is deliberately barred
    from the two stitching stages, which are the Tailor's own work."""

    def test_quality_check_cannot_pass_a_garment_that_was_never_stitched(self):
        """The delivery gate depends on master_quality_check, and QC had no
        guard of its own -- so a Master could pass inspection and mark the order
        Delivered with both stitching stages still NOT_STARTED. The customer's
        tracking page then read "Delivered" over a garment the record says
        nobody made. trial_scheduled already guarded this; QC did not.
        """
        order = self.make_order()

        with self.assertRaises(ValueError) as ctx:
            self.complete(order, "master_quality_check", user=self.master_user)

        self.assertIn("stitching", str(ctx.exception).lower())

    def test_quality_check_passes_once_the_garment_is_stitched(self):
        order = self.make_order()
        self.complete(order, "stitching_completed", user=self.tailor_user)

        self.complete(order, "master_quality_check", user=self.master_user)

        self.assertEqual(self.stage(order, "master_quality_check").status, "COMPLETED")

    def test_a_skipped_stitching_stage_still_allows_quality_check(self):
        """Skip Stage is a real control. A garment the boutique did not stitch
        itself must not be trapped short of QC."""
        order = self.make_order()
        stage = self.stage(order, "stitching_completed")
        stage.status = "SKIPPED"
        stage.save()

        self.complete(order, "master_quality_check", user=self.master_user)

        self.assertEqual(self.stage(order, "master_quality_check").status, "COMPLETED")

    def test_a_master_cannot_do_the_tailors_stitching(self):
        """Not a defect -- the matrix says stitching is ["Owner","Tailor"].
        Pinned so the refusal stays explicit and legible."""
        order = self.make_order()

        with self.assertRaises(ValueError) as ctx:
            self.complete(order, "stitching_completed", user=self.master_user)

        self.assertIn("not authorized", str(ctx.exception).lower())

    def test_a_master_can_take_a_stitched_garment_all_the_way_to_delivered(self):
        """With the tailor's part done, the Master owns every remaining rung."""
        order = self.make_order()
        self.complete(order, "stitching_completed", user=self.tailor_user)

        for key in ["finishing", "pressing", "master_quality_check",
                    "trial_scheduled", "trial_completed", "ready_for_delivery",
                    "delivered"]:
            self.complete(order, key, user=self.master_user)

        order.refresh_from_db()
        self.assertEqual(order.order_status, "Delivered")
