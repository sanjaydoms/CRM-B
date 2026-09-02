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

    def step(self, order, key, status="COMPLETED", user=None):
        """Attempt exactly one transition, and nothing else.

        For tests that assert a transition is refused: they need the order left
        where it is, not helpfully walked into a state where the thing they
        expect to be rejected would succeed.
        """
        return OrderService.transition_order_stage(
            order=order, stage_key=key, new_status=status, user=user or self.owner,
        )

    def reach(self, order, key):
        """Complete everything BEFORE `key`, leaving `key` itself untouched.

        For tests that want to drive the target transition themselves -- to
        check a role, a timestamp or an error -- but now have to get the order
        legitimately to its doorstep first.
        """
        config = BoutiqueSettings.objects.get_or_create(id=1)[0].workflow_config
        keys = [s["key"] for s in config]
        if key not in keys:
            return
        for earlier in keys[:keys.index(key)]:
            stage = order.stages.filter(stage_key=earlier).first()
            if stage is None or stage.status in ("COMPLETED", "SKIPPED"):
                continue
            optional = next(
                (s.get("optional") for s in config if s["key"] == earlier), False)
            OrderService.transition_order_stage(
                order=order, stage_key=earlier,
                new_status="SKIPPED" if optional else "COMPLETED", user=self.owner,
            )

    def complete(self, order, key, user=None):
        """Get this order to `key`, completed -- walking there properly.

        The backend refuses jumps now, so a test that wants an order at quality
        check has to take it through stitching the way the boutique does. This
        used to be a single hop, which was only ever possible because the engine
        permitted a sequence no real order follows. Stages before `key` are
        completed as the owner; the stage itself is attempted as `user`, so role
        gating on the target still bites.
        """
        config = BoutiqueSettings.objects.get_or_create(id=1)[0].workflow_config
        keys = [s["key"] for s in config]
        if key in keys:
            for earlier in keys[:keys.index(key)]:
                stage = order.stages.filter(stage_key=earlier).first()
                if stage is None or stage.status in ("COMPLETED", "SKIPPED"):
                    continue
                optional = next(
                    (s.get("optional") for s in config if s["key"] == earlier), False)
                OrderService.transition_order_stage(
                    order=order, stage_key=earlier,
                    new_status="SKIPPED" if optional else "COMPLETED",
                    user=self.owner,
                )
        return self.step(order, key, user=user)


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
        self.reach(order, "stitching_in_progress")
        OrderService.transition_order_stage(
            order=order, stage_key="stitching_in_progress",
            new_status="IN_PROGRESS", user=self.tailor_user,
        )
        self.assertEqual(self.stage(order, "stitching_in_progress").status, "IN_PROGRESS")

    def test_master_can_run_quality_check(self):
        order = self.make_order()
        self.complete(order, "stitching_completed", user=self.tailor_user)
        self.reach(order, "master_quality_check")
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
            self.step(order, "delivered")
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
        # Walk up to it, so the refusal is about the missing measurements
        # rather than about the stages in between.
        self.reach(order, "assigned_to_tailor")
        with self.assertRaises(ValueError) as ctx:
            self.step(order, "assigned_to_tailor")
        self.assertIn("measurements", str(ctx.exception).lower())

    def test_cannot_schedule_trial_before_stitching_completes(self):
        order = self.make_order()
        with self.assertRaises(ValueError) as ctx:
            self.step(order, "trial_scheduled")
        self.assertIn("stitching", str(ctx.exception).lower())

    def test_rejects_an_unknown_stage(self):
        order = self.make_order()
        with self.assertRaises(ValueError) as ctx:
            self.step(order, "not_a_real_stage")
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
        self.reach(order, "stitching_in_progress")
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

        # Everything except the stage we are about to transition. Pre-setting
        # 'delivered' too would mean asking the engine to complete a stage that
        # is already complete, which it now declines -- re-completing walks an
        # order backwards, which is how a tailor could drop a Delivered order to
        # 'Quality Check' and re-message the customer.
        for conf in BoutiqueSettings.objects.get(id=1).workflow_config:
            if conf["key"] == "delivered":
                continue
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
        self.reach(order, "stitching_in_progress")
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
        # The canonical form. Numbers are stored folded onto one spelling so a
        # returning client is the same record rather than a second profile (see
        # Customer.save); the API returns what is stored, and the interface
        # formats it for reading with formatMobile.
        self.assertEqual(data["customer_mobile"], "919800000077")
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
        self.assertEqual({n["recipient_role"] for n in response.data['results']} - {"Tailor"}, set())

    def test_an_unrecognised_role_returns_nothing_rather_than_everything(self):
        Notification.objects.create(
            recipient_role="Customer", recipient_email="meera@example.test",
            title="Delivered", message="Please complete your remaining balance.",
        )

        response = self._client_for(self.tailor_user).get(
            "/api/notifications/", {"role": "Customer"})

        self.assertEqual(response.status_code, 200)
        roles = {n["recipient_role"] for n in response.data['results']}
        self.assertNotIn("Customer", roles)
        messages = " ".join(n["message"] for n in response.data['results'])
        self.assertNotIn("remaining balance", messages)

    def test_a_tailor_still_receives_their_own_notifications(self):
        Notification.objects.create(
            recipient_role="Tailor", recipient_email="tailor@workflow.test",
            title="Assigned", message="You have been assigned an order.",
        )

        response = self._client_for(self.tailor_user).get("/api/notifications/")

        self.assertEqual(response.status_code, 200)
        titles = [n["title"] for n in response.data['results']]
        self.assertIn("Assigned", titles)
        self.assertEqual({n["recipient_role"] for n in response.data['results']}, {"Tailor"})


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
        # One client-facing status at a time, which is what the control is.
        self._set(order, "Received")
        self._set(order, "Confirmed")
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
        # The state machine now makes this unreachable rather than merely
        # unwise: Ready for Dispatch cannot be entered until quality check is
        # completed, so there is no longer a route to the claim at all. Pinned
        # both ways -- the route is refused, and no such message exists.
        with self.assertRaises(ValueError) as ctx:
            self.step(order, "ready_for_delivery")
        self.assertIn("master quality check", str(ctx.exception).lower())

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
            self.step(order, "master_quality_check", user=self.master_user)

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


class StaffAccountTests(WorkflowTestBase):
    """Creating and editing staff logins. Both defects here made a Master's
    account unusable or, worse, over-privileged."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        token, _ = Token.objects.get_or_create(user=self.owner)
        self.client.credentials(
            HTTP_AUTHORIZATION="Token " + token.key,
            HTTP_X_TENANT_ID=self.tenant.schema_name,
        )

    def test_a_capitalised_email_still_produces_a_usable_login(self):
        """LoginView lowercases the whole input and then matched exactly, while
        the staff bootstrap stored the address as the owner typed it. A Master
        entered as Rohit.Mehra@... got an account that looked correct in Manage
        Tailors and could never be signed in to, with valid credentials.
        """
        response = self.client.post('/api/tailors/', {
            'name': 'Kavya Rao', 'specialty': 'Bridal', 'role': 'Master',
            'email': 'Kavya.Rao@Studio.Test',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)

        tailor = Tailor.objects.get(id=response.data['id'])
        self.assertEqual(tailor.email, 'kavya.rao@studio.test')
        self.assertEqual(tailor.user.username, tailor.user.username.lower())

        # The password is generated per account and returned once, on the
        # response that created it -- there is no shared literal to log in with
        # any more. Reading it from here is the point of returning it: it is
        # exactly what the owner is shown and hands over.
        login = APIClient().post('/api/auth/login/', {
            'username': 'Kavya.Rao@Studio.Test',
            'password': response.data['bootstrap_password'],
        }, format='json')
        self.assertEqual(login.status_code, 200, login.data)
        self.assertEqual(login.data['user']['role'], 'Master')

    def test_changing_a_masters_email_keeps_their_own_login(self):
        """_ensure_user_account looked the account up by email, so changing the
        address created a SECOND user and left the Master's real login attached
        to no Tailor profile -- and resolve_user_role treats a profile-less
        account as the OWNER, so that session silently gained the run of the
        boutique.
        """
        created = self.client.post('/api/tailors/', {
            'name': 'Meena', 'specialty': 'Bridal', 'role': 'Master',
            'email': 'meena@studio.test',
        }, format='json')
        tailor = Tailor.objects.get(id=created.data['id'])
        original_user_id = tailor.user_id
        before = User.objects.count()

        self.client.patch(f"/api/tailors/{tailor.id}/",
                          {'email': 'meena.new@studio.test'}, format='json')

        tailor.refresh_from_db()
        self.assertEqual(tailor.user_id, original_user_id, "login was orphaned")
        self.assertEqual(User.objects.count(), before, "a duplicate account was created")
        tailor.user.refresh_from_db()
        self.assertEqual(tailor.user.email, 'meena.new@studio.test')
        # The account still resolves as a Master, not as the boutique owner.
        from core.roles import resolve_user_role
        self.assertEqual(resolve_user_role(tailor.user), 'Master')


class MasterVerificationChecklistTests(WorkflowTestBase):
    """The one feature built exclusively for a Master."""

    def _client_for(self, user):
        client = APIClient()
        token, _ = Token.objects.get_or_create(user=user)
        client.credentials(
            HTTP_AUTHORIZATION="Token " + token.key,
            HTTP_X_TENANT_ID=self.tenant.schema_name,
        )
        return client

    def test_a_master_can_save_the_checklist(self):
        """It was saved with a plain PATCH of the order, which DRF calls
        partial_update -- an action supervisors are not granted -- so every
        checkbox 403'd for the only role allowed to see the checklist.
        """
        order = self.make_order()
        url = reverse("order-master-verification", args=[order.id])

        response = self._client_for(self.master_user).patch(
            url, {'master_verification': {'cutting': True, 'pressing': False}},
            format='json')

        self.assertEqual(response.status_code, 200, response.data)
        order.refresh_from_db()
        self.assertEqual(order.master_verification, {'cutting': True, 'pressing': False})

    def test_the_checklist_route_cannot_be_used_to_touch_money(self):
        """The narrow action exists precisely so partial_update stays shut --
        that same action carries payment_status and amount_paid.
        """
        order = self.make_order(payment_status='Pending')
        url = reverse("order-master-verification", args=[order.id])

        self._client_for(self.master_user).patch(
            url, {'master_verification': {'cutting': True},
                  'amount_paid': '99999.00', 'payment_status': 'Paid'},
            format='json')

        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'Pending')
        self.assertEqual(order.amount_paid, Decimal('0.00'))

    def test_a_plain_tailor_cannot_save_the_masters_checklist(self):
        order = self.make_order()
        url = reverse("order-master-verification", args=[order.id])

        response = self._client_for(self.tailor_user).patch(
            url, {'master_verification': {'cutting': True}}, format='json')

        self.assertEqual(response.status_code, 403)


class AssignStageTests(WorkflowTestBase):
    """Handing work out -- the supervisor action that is a Master's job."""

    def _client_for(self, user):
        client = APIClient()
        token, _ = Token.objects.get_or_create(user=user)
        client.credentials(
            HTTP_AUTHORIZATION="Token " + token.key,
            HTTP_X_TENANT_ID=self.tenant.schema_name,
        )
        return client

    def test_an_assigned_tailor_can_start_stitching_without_order_tailor(self):
        """The stitching guard read order.tailor, but assign_stage -- the only
        assignment write a Master is permitted -- sets stage.assigned_to.
        Setting order.tailor needs a PATCH of the order, which is Owner-only,
        so a Master's assignment was accepted and then dead-ended.
        """
        order = self.make_order(tailor=False)
        self.reach(order, "stitching_in_progress")
        self._client_for(self.master_user).post(
            reverse("order-assign-stage", args=[order.id]),
            {'stage_key': 'stitching_in_progress', 'tailor_id': self.tailor.id},
            format='json')

        OrderService.transition_order_stage(
            order=order, stage_key='stitching_in_progress',
            new_status='IN_PROGRESS', user=self.tailor_user)

        self.assertEqual(self.stage(order, 'stitching_in_progress').status, 'IN_PROGRESS')

    def test_assigning_tells_the_person_and_leaves_a_record(self):
        """Every other order event notifies and writes an activity row.
        OrderActivity's own field comment lists 'ASSIGNMENT' as an expected
        event_type that nothing ever wrote.
        """
        order = self.make_order()
        before = Notification.objects.count()

        self._client_for(self.master_user).post(
            reverse("order-assign-stage", args=[order.id]),
            {'stage_key': 'stitching_completed', 'tailor_id': self.tailor.id}, format='json')

        self.assertEqual(Notification.objects.count(), before + 1)
        self.assertTrue(order.activities.filter(event_type='ASSIGNMENT').exists())

    def test_the_production_task_follows_the_assignment(self):
        from apps.production.models import ProductionTask

        order = self.make_order()
        self._client_for(self.master_user).post(
            reverse("order-assign-stage", args=[order.id]),
            {'stage_key': 'stitching_in_progress', 'tailor_id': self.tailor.id}, format='json')

        task = ProductionTask.objects.get(order=order, stage_key='stitching_in_progress')
        self.assertEqual(task.assigned_to, self.tailor)

    def test_a_non_numeric_tailor_id_is_a_400_not_a_500(self):
        order = self.make_order()

        response = self._client_for(self.master_user).post(
            reverse("order-assign-stage", args=[order.id]),
            {'stage_key': 'stitching_completed', 'tailor_id': 'not-a-number'}, format='json')

        self.assertEqual(response.status_code, 400)

    def test_a_plain_tailor_cannot_hand_out_work(self):
        order = self.make_order()

        response = self._client_for(self.tailor_user).post(
            reverse("order-assign-stage", args=[order.id]),
            {'stage_key': 'stitching_completed', 'tailor_id': self.tailor.id}, format='json')

        self.assertEqual(response.status_code, 403)


class UpdateStatusAuthorityTests(WorkflowTestBase):
    """update_status is in STAFF_ORDER_ACTIONS so a tailor can drive their own
    stages. Statuses that map to a stage are gated by that stage's role list.
    The ones that map to nothing were gated by nothing at all."""

    def _client_for(self, user):
        client = APIClient()
        token, _ = Token.objects.get_or_create(user=user)
        client.credentials(
            HTTP_AUTHORIZATION="Token " + token.key,
            HTTP_X_TENANT_ID=self.tenant.schema_name,
        )
        return client

    def _set(self, user, order, value):
        return self._client_for(user).patch(
            reverse("order-update-status", args=[order.id]),
            {"status": value}, format="json")

    def test_a_tailor_cannot_tell_the_customer_the_order_shipped(self):
        """'Shipped' maps to no stage, so it fell into the branch that writes
        order_status directly and fires create_order_notifications -- the only
        message carrying the courier name and tracking number. Any tailor could
        send it.
        """
        order = self.make_order()

        response = self._set(self.tailor_user, order, "Shipped")

        self.assertEqual(response.status_code, 403)
        order.refresh_from_db()
        self.assertNotEqual(order.order_status, "Shipped")

    def test_an_arbitrary_string_is_not_an_order_status(self):
        """The endpoint stored whatever it was handed, so an order's status --
        shown to the customer on the tracking page -- could be any text at all.
        """
        order = self.make_order()

        response = self._set(self.owner, order, "Totally Made Up")

        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertNotEqual(order.order_status, "Totally Made Up")

    def test_a_supervisor_can_still_move_a_stageless_status(self):
        order = self.make_order()

        response = self._set(self.master_user, order, "Stylist Review")

        self.assertEqual(response.status_code, 200, response.data)
        order.refresh_from_db()
        self.assertEqual(order.order_status, "Stylist Review")

    def test_a_tailor_can_still_drive_their_own_stage(self):
        """The gate must not cost a tailor the thing update_status is in
        STAFF_ORDER_ACTIONS for."""
        order = self.make_order()
        # The bands before this one are the owner's and the master's work;
        # the tailor picks the garment up from there.
        self.reach(order, "stitching_in_progress")

        response = self._set(self.tailor_user, order, "Design & Creation")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.stage(order, "stitching_completed").status, "COMPLETED")


class NotificationBellTests(WorkflowTestBase):
    """The bell is on every screen, so its permissions are load-bearing."""

    def _client_for(self, user):
        client = APIClient()
        token, _ = Token.objects.get_or_create(user=user)
        client.credentials(
            HTTP_AUTHORIZATION="Token " + token.key,
            HTTP_X_TENANT_ID=self.tenant.schema_name,
        )
        return client

    def test_staff_can_clear_their_own_notifications(self):
        """mark-all-read is a POST, and NotificationViewSet used the default
        RolePermission, which grants a non-Owner only the named order actions
        as writes. Every staff member got a 403 opening the drawer -- and the
        frontend threw it inside the click handler, dropping the whole
        application to its runtime-error screen. A tailor lost the app on their
        first click of a control present on every page.
        """
        Notification.objects.create(
            recipient_role="Tailor", recipient_email="tailor@workflow.test",
            title="Assigned", message="You have work.", is_read=False)

        response = self._client_for(self.tailor_user).post(
            "/api/notifications/mark-all-read/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(
            Notification.objects.filter(recipient_role="Tailor", is_read=False).exists())

    def test_clearing_does_not_touch_anybody_elses_feed(self):
        """Safe without a role check only because get_queryset scopes to the
        caller -- so pin that."""
        Notification.objects.create(
            recipient_role="Owner", recipient_email="owner@workflow.test",
            title="Owner only", message="Turnover.", is_read=False)

        self._client_for(self.tailor_user).post("/api/notifications/mark-all-read/")

        self.assertTrue(
            Notification.objects.filter(recipient_role="Owner", is_read=False).exists())


class CrossRouterScopingTests(WorkflowTestBase):
    """RolePermission grants every non-Owner staff member all SAFE_METHODS.
    That is only safe because each viewset narrows its own queryset -- a promise
    the routers outside crm_api never made, so a tailor read the whole boutique
    through them."""

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
        self.mine = self.make_order()
        stranger = self.make_customer(mobile="9800000077")
        stranger.email_address = "stranger@client.test"
        stranger.address = "9 Secret Lane"
        stranger.save()
        self.stranger = stranger
        self.not_mine = self.make_order(customer=stranger, tailor=False, master=False)

    def test_appointments_do_not_hand_over_a_strangers_contact_details(self):
        """AppointmentSerializer nests the full CustomerSerializer, which nests
        that customer's orders and their money -- and the frontend loads this
        endpoint for every role on every login, so it arrived unasked.
        """
        from apps.scheduling.models import Appointment
        from django.utils import timezone
        Appointment.objects.create(
            customer=self.stranger, scheduled_time=timezone.now(), appointment_type='TRIAL')

        response = self._client_for(self.tailor_user).get('/api/scheduling/appointments/')

        self.assertEqual(response.status_code, 200)
        payload = str(response.data)
        self.assertNotIn('Secret Lane', payload)
        self.assertNotIn('stranger@client.test', payload)

    def test_production_tasks_are_scoped_to_the_callers_own_orders(self):
        response = self._client_for(self.tailor_user).get('/api/production/tasks/')

        self.assertEqual(response.status_code, 200)
        order_ids = {t['order'] for t in response.data['results']}
        self.assertNotIn(self.not_mine.id, order_ids)

    def test_the_activity_log_is_not_open_to_the_whole_floor(self):
        response = self._client_for(self.tailor_user).get('/api/activities/activities/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 0)

    def test_supplier_trading_terms_are_owner_only(self):
        response = self._client_for(self.tailor_user).get('/api/inventory/suppliers/')

        self.assertEqual(response.status_code, 403)

    def test_a_colleagues_login_address_is_not_on_the_staff_list(self):
        response = self._client_for(self.tailor_user).get('/api/tailors/')

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('email', response.data['results'][0])
        # The owner still needs it -- that is the screen which mints logins.
        owner_view = self._client_for(self.owner).get('/api/tailors/')
        self.assertIn('email', owner_view.data['results'][0])


class DeliveryGateTests(WorkflowTestBase):
    """Nothing reaches the customer as Delivered without passing QC.

    The gate existed but was written `stage_key == 'delivered' and new_status
    == 'COMPLETED'`, while the status map wrote 'Delivered' for EVERY new_status
    on that stage. The frontend offers "Start In-Progress" on any NOT_STARTED or
    PAUSED stage and "Skip Stage" on any non-COMPLETED one, both posting through
    transition_order_stage -- so the two most obvious buttons on the row walked
    straight past the one hard invariant in the workflow, flipped the public
    tracking page, and drafted the customer a message asking for the balance on
    a garment nobody had inspected.
    """

    def _order_at_delivery(self):
        order = self.make_order()
        for key in ('created', 'measurements_completed', 'fabric_confirmed',
                    'pattern_cutting', 'assigned_to_tailor',
                    'stitching_in_progress', 'stitching_completed'):
            stage = order.stages.filter(stage_key=key).first()
            if stage:
                self.complete(order, key)
        return order

    def test_skipping_delivery_cannot_mark_an_uninspected_order_delivered(self):
        order = self._order_at_delivery()
        self.assertNotEqual(
            self.stage(order, 'master_quality_check').status, 'COMPLETED')
        with self.assertRaises(ValueError):
            OrderService.transition_order_stage(
                order=order, stage_key='delivered', new_status='SKIPPED',
                user=self.owner)
        order.refresh_from_db()
        self.assertNotEqual(order.order_status, 'Delivered')

    def test_starting_delivery_cannot_mark_an_uninspected_order_delivered(self):
        order = self._order_at_delivery()
        with self.assertRaises(ValueError):
            OrderService.transition_order_stage(
                order=order, stage_key='delivered', new_status='IN_PROGRESS',
                user=self.owner)
        order.refresh_from_db()
        self.assertNotEqual(order.order_status, 'Delivered')

    def test_starting_delivery_after_qc_does_not_yet_announce_delivery(self):
        # Picking the parcel up is not the same as the customer having it. The
        # status must not move until the stage is COMPLETED.
        order = self._order_at_delivery()
        self.reach(order, 'delivered')
        before = Order.objects.get(pk=order.pk).order_status
        OrderService.transition_order_stage(
            order=order, stage_key='delivered', new_status='IN_PROGRESS',
            user=self.owner)
        order.refresh_from_db()
        self.assertEqual(order.order_status, before)
        self.assertNotEqual(order.order_status, 'Delivered')

    def test_completing_delivery_after_qc_still_works(self):
        # The gate must not have become a wall.
        order = self._order_at_delivery()
        for key in ('finishing', 'pressing', 'master_quality_check'):
            if order.stages.filter(stage_key=key).exists():
                self.complete(order, key)
        self.complete(order, 'delivered')
        order.refresh_from_db()
        self.assertEqual(order.order_status, 'Delivered')


class MasterVerificationMergeTests(WorkflowTestBase):
    """Ticking a second box must not undo the first.

    Both screens that render the checklist build their payload by spreading the
    order out of the dashboard's cached list, so the second tick posts a copy
    taken before the first was saved. The endpoint replaced the stored object
    wholesale, so the Master watched their own ticks come undone -- and what
    was recorded afterwards was not what had been verified.
    """

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        token, _ = Token.objects.get_or_create(user=self.owner)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token.key,
                                HTTP_X_TENANT_ID=self.tenant.schema_name)
        self.order = self.make_order()

    def _patch(self, checks):
        return self.client.patch(
            f'/api/orders/{self.order.id}/master-verification/',
            {'master_verification': checks}, format='json')

    def test_a_second_tick_keeps_the_first(self):
        self._patch({'stitching': True})
        response = self._patch({'finishing': True})
        self.assertEqual(response.status_code, 200, response.data)
        self.order.refresh_from_db()
        self.assertEqual(self.order.master_verification,
                         {'stitching': True, 'finishing': True})

    def test_a_stale_payload_cannot_erase_a_saved_tick(self):
        # Exactly the frontend's behaviour: post the object as it was before
        # the earlier tick landed.
        self._patch({'stitching': True})
        self._patch({'finishing': True})
        self._patch({'stitching': True, 'pressing': True})   # stale: no finishing
        self.order.refresh_from_db()
        self.assertEqual(
            self.order.master_verification,
            {'stitching': True, 'finishing': True, 'pressing': True})

    def test_unticking_still_works(self):
        self._patch({'stitching': True})
        self._patch({'stitching': False})
        self.order.refresh_from_db()
        self.assertEqual(self.order.master_verification, {'stitching': False})


class SareeMeasurementTests(WorkflowTestBase):
    """A saree-only order must not stall on measurements it never asked for.

    bust/waist/hips are written only by the wizard's CUSTOMER_KEYS map, and the
    saree template's measurement section carries petticoat_length and
    petticoat_waist -- neither of which is in that map. So all three columns
    stayed NULL and the order stopped at "Cannot assign tailor. Measurements are
    not completed for this customer", naming a step the wizard never offered for
    a garment with no bust measurement to take.
    """

    def test_a_garment_snapshot_counts_as_having_been_measured(self):
        from apps.catalog.models import GarmentJob, GarmentTemplate
        customer = self.make_customer(mobile="9800000077", with_measurements=False)
        order = self.make_order(customer=customer)
        template = GarmentTemplate.objects.first()
        self.assertIsNotNone(template, "templates are seeded per tenant")
        GarmentJob.objects.create(
            order=order, template=template,
            measurements={'petticoat_length': 40, 'petticoat_waist': 30},
        )
        self.complete(order, 'created')
        # The stage that used to raise.
        self.complete(order, 'assigned_to_tailor')
        self.assertEqual(self.stage(order, 'assigned_to_tailor').status, 'COMPLETED')

    def test_an_order_with_nothing_measured_anywhere_is_still_refused(self):
        # The guard must not have been removed, only widened.
        customer = self.make_customer(mobile="9800000078", with_measurements=False)
        order = self.make_order(customer=customer)
        self.reach(order, 'assigned_to_tailor')
        with self.assertRaises(ValueError):
            self.step(order, 'assigned_to_tailor')


class CustomerSpendAggregateTests(WorkflowTestBase):
    """Lifetime spend must count orders, not distinct prices.

    Sum(DISTINCT total_amount) de-duplicates by VALUE, so two orders at the same
    price totalled one of them. Repeat orders at a repeated price point are the
    ordinary pattern in a boutique. The existing coverage used three different
    amounts, which is why this survived.
    """

    def _summary_for(self, customer, user):
        from domains.customers.repositories import CustomerRepository
        from core.permissions import visible_customers
        rows = visible_customers(CustomerRepository.summary_queryset(), user)
        return rows.get(pk=customer.pk)

    def test_two_orders_at_the_same_price_are_both_counted(self):
        customer = self.make_customer(mobile="9800000101")
        self.make_order(customer=customer, base_price=40000)
        self.make_order(customer=customer, base_price=40000)
        row = self._summary_for(customer, self.owner)
        self.assertEqual(row.orders_count, 2)
        # Two identical orders must total twice one of them, not once.
        one_order_total = Order.objects.filter(customer=customer).first().total_amount
        self.assertEqual(row.orders_total_spend, one_order_total * 2)

    def test_three_identical_orders_still_add_up(self):
        customer = self.make_customer(mobile="9800000102")
        for _ in range(3):
            self.make_order(customer=customer, base_price=25000)
        row = self._summary_for(customer, self.owner)
        self.assertEqual(row.orders_count, 3)
        one = Order.objects.filter(customer=customer).first().total_amount
        self.assertEqual(row.orders_total_spend, one * 3)

    def test_differing_prices_are_unaffected(self):
        # The case the old code got right; it must stay right.
        customer = self.make_customer(mobile="9800000103")
        self.make_order(customer=customer, base_price=10000)
        self.make_order(customer=customer, base_price=25000)
        row = self._summary_for(customer, self.owner)
        expected = sum(o.total_amount for o in Order.objects.filter(customer=customer))
        self.assertEqual(row.orders_total_spend, expected)

    def test_a_tailors_view_is_not_multiplied_by_the_stage_join(self):
        # The fan-out distinct=True was originally added to counter. Removing
        # distinct must not bring the fifteen-times-too-large figure back.
        customer = self.make_customer(mobile="9800000104")
        self.make_order(customer=customer, base_price=40000)
        self.make_order(customer=customer, base_price=40000)
        expected = sum(o.total_amount for o in Order.objects.filter(customer=customer))
        row = self._summary_for(customer, self.tailor_user)
        self.assertEqual(row.orders_count, 2)
        self.assertEqual(row.orders_total_spend, expected)

    def test_a_tailor_still_sees_only_their_own_clients(self):
        # The scoping rewrite must not have widened disclosure. A customer whose
        # orders belong to nobody this tailor works on stays invisible.
        from domains.customers.repositories import CustomerRepository
        from core.permissions import visible_customers
        other_tailor = Tailor.objects.create(
            name="Ira Nathan", specialty="Gowns", role="Tailor", status="Available")
        mine = self.make_customer(mobile="9800000105")
        self.make_order(customer=mine, base_price=12000)
        theirs = self.make_customer(mobile="9800000106")
        OrderService.create_order_for_customer(
            theirs, {"base_price": 12000, "tailor_id": other_tailor.id,
                     "master_id": other_tailor.id}, user=self.owner)

        visible = visible_customers(
            CustomerRepository.summary_queryset(), self.tailor_user)
        ids = set(visible.values_list('pk', flat=True))
        self.assertIn(mine.pk, ids)
        self.assertNotIn(theirs.pk, ids)

    def test_the_scoped_list_has_no_duplicate_rows(self):
        # .distinct() was dropped along with the join; the subquery must be
        # doing that work now, or every customer appears once per stage.
        from domains.customers.repositories import CustomerRepository
        from core.permissions import visible_customers
        customer = self.make_customer(mobile="9800000107")
        self.make_order(customer=customer, base_price=15000)
        rows = list(visible_customers(
            CustomerRepository.summary_queryset(), self.tailor_user)
            .values_list('pk', flat=True))
        self.assertEqual(len(rows), len(set(rows)), f"duplicate rows: {rows}")


class ReassignmentTests(WorkflowTestBase):
    """Moving an order to another tailor must move everything with it.

    perform_update did only save(), _reconcile_payment and a status
    notification -- so the departing tailor still read Busy with nothing on
    their table, the arriving one still read Available with a dress to sew, the
    production task still named the old person, and nobody was told. Those two
    badges are what the owner picks staff by.
    """

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        token, _ = Token.objects.get_or_create(user=self.owner)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token.key,
                                HTTP_X_TENANT_ID=self.tenant.schema_name)
        self.other = Tailor.objects.create(
            name="Ira Nathan", specialty="Gowns", role="Tailor", status="Available")
        self.order = self.make_order()

    def _reassign_to(self, tailor):
        return self.client.patch(f'/api/orders/{self.order.id}/',
                                 {'tailor': tailor.id}, format='json')

    def test_both_tailors_availability_is_recomputed(self):
        self.tailor.refresh_from_db()
        self.assertEqual(self.tailor.status, 'Busy')

        response = self._reassign_to(self.other)
        self.assertEqual(response.status_code, 200, response.data)

        self.tailor.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(self.other.status, 'Busy')
        self.assertEqual(self.tailor.status, 'Available')

    def test_the_production_task_follows_the_order(self):
        from apps.production.models import ProductionTask
        self.assertTrue(ProductionTask.objects.filter(
            order=self.order, assigned_to=self.tailor).exists())

        self._reassign_to(self.other)

        self.assertFalse(ProductionTask.objects.filter(
            order=self.order, assigned_to=self.tailor).exists())
        self.assertTrue(ProductionTask.objects.filter(
            order=self.order, assigned_to=self.other).exists())

    def test_the_new_tailor_is_told(self):
        from crm_api.models import Notification
        before = Notification.objects.count()
        self._reassign_to(self.other)
        self.assertGreater(Notification.objects.count(), before)
        note = Notification.objects.filter(
            title__contains=self.order.order_id).order_by('-id').first()
        self.assertIsNotNone(note)
        # The person's OWN role, so their feed actually matches it.
        self.assertEqual(note.recipient_role, self.other.role)

    def test_a_specialist_master_is_notified_under_their_own_role(self):
        # The four literal "Tailor"/"Master" recipient_roles meant a specialist
        # never saw work assigned to them: the feed filters on profile.role.
        cutting = Tailor.objects.create(
            name="Ravi Pattern", specialty="Cutting", role="Cutting Master",
            status="Available")
        self._reassign_to(cutting)
        from crm_api.models import Notification
        note = Notification.objects.filter(
            title__contains=self.order.order_id).order_by('-id').first()
        self.assertEqual(note.recipient_role, 'Cutting Master')

    def test_a_plain_edit_does_not_touch_assignment(self):
        # Only a genuine reassignment should fire any of this.
        from crm_api.models import Notification
        before = Notification.objects.count()
        response = self.client.patch(f'/api/orders/{self.order.id}/',
                                     {'custom_requirements': 'Add piping'},
                                     format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Notification.objects.count(), before)


class ReversalTests(WorkflowTestBase):
    """The two sanctioned ways backwards: supervised reopen and QC-fail rework.

    Everything else stays refused -- that is what makes a status a fact.
    """

    def setUp(self):
        super().setUp()
        self.designer_user = User.objects.create_user(
            username="designer@workflow.test", email="designer@workflow.test",
            password="designerpass123", first_name="Devi",
        )
        from apps.design_studio.models import Designer
        Designer.objects.create(name="Devi", user=self.designer_user)

    def reopen(self, order, key, user=None, reason="wrong button"):
        from domains.orders.services import reopen_order_stage
        return reopen_order_stage(order, key, user=user or self.owner, reason=reason)

    def fail_qc(self, order, user=None, reason="hem is crooked"):
        from domains.orders.services import fail_quality_check
        return fail_quality_check(order, user=user or self.master_user, reason=reason)

    # ---- supervised reopen ----

    def test_owner_reopens_frontier_stage_with_reason(self):
        order = self.make_order()
        self.complete(order, "measurements_completed")
        self.reopen(order, "measurements_completed", user=self.owner)
        stage = self.stage(order, "measurements_completed")
        self.assertEqual(stage.status, "IN_PROGRESS")
        self.assertIsNone(stage.completed_at)
        order.refresh_from_db()
        self.assertEqual(order.production_status, "IN_PROGRESS")
        self.assertEqual(order.current_stage_key, "measurements_completed")
        # The record says who, what and why.
        from crm_api.models import OrderActivity
        event = OrderActivity.objects.filter(
            order=order, event_type="STAGE_REOPENED").latest("timestamp")
        self.assertEqual(event.metadata["reason"], "wrong button")
        self.assertEqual(event.metadata["previous_status"], "COMPLETED")

    def test_master_may_reopen_but_tailor_and_designer_may_not(self):
        order = self.make_order()
        self.complete(order, "measurements_completed")
        for outsider in (self.tailor_user, self.designer_user):
            with self.assertRaises(PermissionError):
                self.reopen(order, "measurements_completed", user=outsider)
        self.reopen(order, "measurements_completed", user=self.master_user)
        self.assertEqual(
            self.stage(order, "measurements_completed").status, "IN_PROGRESS")

    def test_reopen_requires_a_reason(self):
        order = self.make_order()
        self.complete(order, "measurements_completed")
        from domains.orders.workflow import TransitionError
        with self.assertRaises(TransitionError):
            self.reopen(order, "measurements_completed", reason="   ")

    def test_only_the_frontier_stage_can_be_reopened(self):
        order = self.make_order()
        self.complete(order, "fabric_confirmed")
        from domains.orders.workflow import TransitionError
        with self.assertRaises(TransitionError):
            self.reopen(order, "measurements_completed")
        # The refused call changed nothing.
        self.assertEqual(
            self.stage(order, "measurements_completed").status, "COMPLETED")

    def test_reopen_drops_client_status_to_what_remains_true(self):
        order = self.make_order()
        self.complete(order, "master_quality_check")
        order.refresh_from_db()
        self.assertEqual(order.order_status, "Ready for Dispatch")
        self.reopen(order, "master_quality_check")
        order.refresh_from_db()
        self.assertEqual(order.order_status, "Quality Check")

    def test_reopened_skipped_stage_returns_to_not_started(self):
        order = self.make_order()
        self.reach(order, "assigned_to_tailor")
        self.assertEqual(self.stage(order, "maggam_work").status, "SKIPPED")
        self.reopen(order, "maggam_work")
        self.assertEqual(self.stage(order, "maggam_work").status, "NOT_STARTED")

    # ---- QC-fail rework ----

    def test_qc_fail_reopens_the_stitching_band(self):
        order = self.make_order()
        self.reach(order, "master_quality_check")
        self.step(order, "master_quality_check", status="IN_PROGRESS",
                  user=self.master_user)
        self.fail_qc(order)
        self.assertEqual(
            self.stage(order, "stitching_in_progress").status, "IN_PROGRESS")
        self.assertEqual(
            self.stage(order, "stitching_completed").status, "NOT_STARTED")
        self.assertEqual(self.stage(order, "finishing").status, "NOT_STARTED")
        self.assertEqual(self.stage(order, "pressing").status, "NOT_STARTED")
        qc = self.stage(order, "master_quality_check")
        self.assertEqual(qc.status, "NOT_STARTED")
        self.assertIn("QC FAILED: hem is crooked", qc.comments)
        order.refresh_from_db()
        self.assertEqual(order.order_status, "Design & Creation")
        self.assertEqual(order.current_stage_key, "stitching_in_progress")

    def test_qc_fail_requires_reason_and_role(self):
        order = self.make_order()
        self.reach(order, "master_quality_check")
        from domains.orders.workflow import TransitionError
        with self.assertRaises(TransitionError):
            self.fail_qc(order, reason="")
        with self.assertRaises(PermissionError):
            self.fail_qc(order, user=self.tailor_user)

    def test_qc_master_can_fail_a_check(self):
        qc_user = User.objects.create_user(
            username="qc@workflow.test", email="qc@workflow.test",
            password="qcpass123", first_name="Quill",
        )
        Tailor.objects.create(
            name="Quill", specialty="QC", role="QC Master",
            status="Available", user=qc_user,
        )
        order = self.make_order()
        self.reach(order, "master_quality_check")
        self.fail_qc(order, user=qc_user, reason="loose thread on sleeve")
        self.assertEqual(
            self.stage(order, "master_quality_check").status, "NOT_STARTED")

    def test_qc_fail_refused_before_stitching_is_done(self):
        order = self.make_order()
        self.complete(order, "fabric_confirmed")
        from domains.orders.workflow import TransitionError
        with self.assertRaises(TransitionError):
            self.fail_qc(order)

    def test_qc_fail_refused_after_qc_passed(self):
        order = self.make_order()
        self.complete(order, "master_quality_check")
        from domains.orders.workflow import TransitionError
        with self.assertRaises(TransitionError):
            self.fail_qc(order)

    def test_rework_loop_can_run_forward_again(self):
        """The loop closes: fail, re-stitch, pass, and the record is coherent."""
        order = self.make_order()
        self.reach(order, "master_quality_check")
        self.fail_qc(order)
        self.complete(order, "master_quality_check")
        order.refresh_from_db()
        self.assertEqual(order.order_status, "Ready for Dispatch")

    # ---- the endpoints ----

    def api(self, user):
        client = APIClient()
        token, _ = Token.objects.get_or_create(user=user)
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return client

    def test_reopen_endpoint_refuses_tailor_with_403(self):
        order = self.make_order()
        self.complete(order, "measurements_completed")
        res = self.api(self.tailor_user).post(
            f"/api/orders/{order.id}/reopen-stage/",
            {"stage_key": "measurements_completed", "reason": "nope"},
            format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_reopen_endpoint_works_for_master(self):
        order = self.make_order()
        self.complete(order, "measurements_completed")
        res = self.api(self.master_user).post(
            f"/api/orders/{order.id}/reopen-stage/",
            {"stage_key": "measurements_completed", "reason": "measured the wrong client"},
            format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.stage(order, "measurements_completed").status, "IN_PROGRESS")

    def test_fail_qc_endpoint_round_trip(self):
        order = self.make_order()
        self.reach(order, "master_quality_check")
        res = self.api(self.master_user).post(
            f"/api/orders/{order.id}/fail-qc/",
            {"reason": "lining puckers at the waist"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["order_status"], "Design & Creation")

    # ---- the closed backdoor and the honest read model ----

    def test_settled_skipped_stage_refuses_backward_transition_for_everyone(self):
        """The /transition/ route cannot reverse a settled stage -- not even for
        the owner. That door is reopen-stage, which demands a reason."""
        order = self.make_order()
        self.reach(order, "assigned_to_tailor")
        self.assertEqual(self.stage(order, "maggam_work").status, "SKIPPED")
        from domains.orders.workflow import TransitionError
        for actor in (self.owner, self.master_user, self.tailor_user):
            with self.assertRaises(TransitionError):
                self.step(order, "maggam_work", status="IN_PROGRESS", user=actor)
        # Forward out of SKIPPED stays open: the optional work was done after all.
        self.step(order, "maggam_work", status="COMPLETED", user=self.master_user)
        self.assertEqual(self.stage(order, "maggam_work").status, "COMPLETED")

    def test_reversals_keep_production_tasks_in_step(self):
        from apps.production.models import ProductionTask
        order = self.make_order()
        self.reach(order, "master_quality_check")
        self.fail_qc(order)
        stitching_task = ProductionTask.objects.get(
            order=order, stage_key="stitching_in_progress")
        self.assertEqual(stitching_task.status, "IN_PROGRESS")
        qc_task = ProductionTask.objects.get(
            order=order, stage_key="master_quality_check")
        self.assertEqual(qc_task.status, "PENDING")
