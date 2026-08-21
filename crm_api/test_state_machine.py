"""The workflow is a state machine, and the backend is where it is enforced.

The bug these exist for: `POST /transition/` accepted any stage in any order.
An order sitting in pattern cutting could be moved straight to Ready for
Dispatch with a 200, and the customer's tracking page said so while stitching,
finishing, pressing and quality check were all NOT_STARTED. Hiding buttons in
the UI does not fix that -- the request is what has to be refused.

Two properties matter as much as the rules themselves, and both are tested
here rather than assumed:

  a rejected transition changes NOTHING -- not the stage, the order status,
  stock, reservations, the activity log, the timestamps or the assignments;

  a repeated transition changes nothing FURTHER -- a double-click, a retried
  POST or a stale browser tab must not consume material twice, log twice or
  message the customer twice.
"""

from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django_tenants.test.cases import TenantTestCase

from apps.catalog.models import GarmentJob, GarmentTemplate, JobMaterial
from apps.inventory.models import Category, InventoryItem, StockMovement, Unit
from apps.inventory.services import InventoryService
from crm_api.models import (
    BoutiqueSettings, Customer, CustomerMessage, Order, OrderActivity, OrderStage,
    Tailor,
)
from domains.orders import workflow
from domains.orders.services import OrderService

#: The workflow in order, as get_default_workflow declares it.
SEQUENCE = [
    'created', 'measurements_completed', 'fabric_confirmed', 'pattern_cutting',
    'maggam_work', 'assigned_to_tailor', 'stitching_in_progress',
    'stitching_completed', 'finishing', 'pressing', 'master_quality_check',
    'trial_scheduled', 'trial_completed', 'ready_for_delivery', 'delivered',
]


class StateMachineTestBase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@statemachine.test"
        tenant.name = "State Machine Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        from django.db import connection
        connection.set_tenant(self.tenant)

        self.owner = User.objects.create_user(
            username="owner@statemachine.test", email="owner@statemachine.test",
            password="ownerpass123")
        self.tailor_user = User.objects.create_user(
            username="tailor@statemachine.test", email="tailor@statemachine.test",
            password="tailorpass123")
        self.tailor = Tailor.objects.create(
            name="Sunita Devi", specialty="Stitching", role="Tailor",
            user=self.tailor_user)
        self.master_user = User.objects.create_user(
            username="master@statemachine.test", email="master@statemachine.test",
            password="masterpass123")
        self.master = Tailor.objects.create(
            name="Ravi Kumar", specialty="Cutting", role="Master",
            user=self.master_user)

        BoutiqueSettings.objects.get_or_create(id=1)
        self.customer = Customer.objects.create(
            first_name="Lakshmi", last_name="Iyer", mobile_number="919845012345",
            email_address="lakshmi@statemachine.test", address="44 Church Street",
            customer_type="Women", garment_type="Blouse")
        self.template = GarmentTemplate.objects.create(
            key='blouse', name='Blouse', version=1, sequence=0)
        self.brocade = InventoryItem.objects.create(
            item_code='FAB-001', name='Maroon Brocade', category=Category.FABRIC,
            unit=Unit.METER, purchase_price=Decimal('100'), reorder_level=Decimal('5'))
        InventoryService.stock_in(self.brocade, Decimal('25'), user=self.owner,
                                  remarks='Opening')

        self.order = self._order()

    def _order(self, order_id="T2B-SM-1", with_materials=True):
        order = Order.objects.create(
            order_id=order_id, customer=self.customer, total_amount=Decimal('1000'),
            tailor=self.tailor, master=self.master)
        config = BoutiqueSettings.objects.get(id=1).workflow_config
        for seq, conf in enumerate(config):
            OrderStage.objects.create(
                order=order, stage_key=conf['key'], stage_name=conf['name'],
                sequence=seq, sla_hours=conf.get('sla_hours', 24))
        job = GarmentJob.objects.create(
            order=order, template=self.template, template_version=1,
            spec={}, measurements={'chest': '36'}, sequence=0)
        if with_materials:
            JobMaterial.objects.create(
                job=job, field_key='main_fabric', inventory_item=self.brocade,
                quantity=Decimal('2'), unit=Unit.METER,
                source=JobMaterial.Source.STORE)
        return order

    def move(self, stage_key, status='COMPLETED', user=None, order=None):
        return OrderService.transition_order_stage(
            order=order or self.order, stage_key=stage_key, new_status=status,
            user=user or self.owner)

    def advance_to(self, stage_key, order=None):
        """Walk the workflow properly up to (not including) a stage."""
        order = order or self.order
        for key in SEQUENCE[:SEQUENCE.index(stage_key)]:
            status = 'SKIPPED' if workflow.is_optional(
                BoutiqueSettings.objects.get(id=1).workflow_config, key) else 'COMPLETED'
            self.move(key, status, order=order)

    def snapshot(self, order=None):
        """Everything a rejected transition must leave untouched."""
        order = order or self.order
        order.refresh_from_db()
        self.brocade.refresh_from_db()
        return {
            'order_status': order.order_status,
            'current_stage': order.current_stage_key,
            'stages': dict(order.stages.values_list('stage_key', 'status')),
            'started': dict(order.stages.values_list('stage_key', 'started_at')),
            'completed': dict(order.stages.values_list('stage_key', 'completed_at')),
            'tailor': order.tailor_id,
            'master': order.master_id,
            'stock': self.brocade.current_stock,
            'reserved': self.brocade.reserved_stock,
            'movements': StockMovement.objects.filter(order=order).count(),
            'activities': OrderActivity.objects.filter(order=order).count(),
            'messages': CustomerMessage.objects.filter(order=order).count(),
        }


class InvalidTransitionTests(StateMachineTestBase):

    def test_pattern_cutting_to_ready_for_dispatch_is_refused(self):
        """The exact request that used to return 200 in production."""
        self.advance_to('maggam_work')          # through pattern cutting
        before = self.snapshot()

        with self.assertRaises(ValueError) as caught:
            self.move('ready_for_delivery')

        self.assertIn('not completed', str(caught.exception))
        self.assertEqual(self.snapshot(), before, 'a refusal must change nothing')

    def test_a_refused_transition_leaves_absolutely_everything_alone(self):
        self.advance_to('fabric_confirmed')
        self.move('fabric_confirmed')           # reserves material
        before = self.snapshot()
        self.assertGreater(before['reserved'], 0, 'precondition: something is reserved')

        with self.assertRaises(ValueError):
            self.move('delivered')

        self.assertEqual(self.snapshot(), before)

    def test_a_mandatory_stage_cannot_be_skipped(self):
        self.advance_to('pressing')
        before = self.snapshot()
        with self.assertRaises(ValueError) as caught:
            self.move('pressing', 'SKIPPED')
        self.assertIn('cannot be skipped', str(caught.exception))
        self.assertEqual(self.snapshot(), before)

    def test_an_optional_stage_may_be_skipped(self):
        """`optional` is what licenses SKIPPED -- and only that."""
        self.advance_to('maggam_work')
        self.move('maggam_work', 'SKIPPED')
        self.assertEqual(
            self.order.stages.get(stage_key='maggam_work').status, 'SKIPPED')
        # ...and the workflow continues past it.
        self.move('assigned_to_tailor')
        self.assertEqual(
            self.order.stages.get(stage_key='assigned_to_tailor').status, 'COMPLETED')

    def test_an_unknown_stage_is_refused(self):
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.move('teleport_to_delivery')
        self.assertEqual(self.snapshot(), before)

    def test_an_invalid_status_is_refused(self):
        before = self.snapshot()
        with self.assertRaises(ValueError) as caught:
            self.move('fabric_confirmed', 'BANANA')
        self.assertIn('Invalid stage status', str(caught.exception))
        self.assertEqual(self.snapshot(), before)

    def test_a_completed_stage_cannot_be_reopened(self):
        """Backward moves walked the whole order -- and the customer -- back."""
        self.advance_to('fabric_confirmed')
        self.move('fabric_confirmed')
        before = self.snapshot()

        with self.assertRaises(ValueError) as caught:
            self.move('fabric_confirmed', 'IN_PROGRESS')

        self.assertIn('already completed', str(caught.exception))
        self.assertEqual(self.snapshot(), before)

    def test_nothing_moves_after_delivery(self):
        for key in SEQUENCE:
            status = 'SKIPPED' if key == 'maggam_work' else 'COMPLETED'
            self.move(key, status)
        self.assertEqual(self.order.stages.get(stage_key='delivered').status,
                         'COMPLETED')
        before = self.snapshot()

        with self.assertRaises(ValueError):
            self.move('delivered', 'IN_PROGRESS')
        with self.assertRaises(ValueError):
            self.move('pressing', 'IN_PROGRESS')

        self.assertEqual(self.snapshot(), before)

    def test_an_unauthorised_role_is_refused(self):
        """A tailor cannot pass the boutique's own quality check."""
        self.advance_to('master_quality_check')
        before = self.snapshot()
        with self.assertRaises(ValueError) as caught:
            self.move('master_quality_check', user=self.tailor_user)
        self.assertIn('not authorized', str(caught.exception))
        self.assertEqual(self.snapshot(), before)

    def test_a_stage_missing_its_required_data_is_refused(self):
        """Ordering cannot express "somebody must be holding the garment"."""
        order = self._order(order_id="T2B-SM-NOTAILOR")
        order.tailor = None
        order.save(update_fields=['tailor'])
        self.advance_to('stitching_in_progress', order=order)

        with self.assertRaises(ValueError) as caught:
            self.move('stitching_in_progress', 'IN_PROGRESS', order=order)
        self.assertIn('No tailor is assigned', str(caught.exception))


class ValidSequenceTests(StateMachineTestBase):

    def test_the_whole_workflow_runs_in_order(self):
        for key in SEQUENCE:
            status = 'SKIPPED' if key == 'maggam_work' else 'COMPLETED'
            self.move(key, status)
            self.assertEqual(
                self.order.stages.get(stage_key=key).status, status,
                f'{key} did not reach {status}')

        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, 'Delivered')
        self.assertEqual(self.order.current_stage_key, 'delivered')

    def test_each_stage_refuses_until_its_predecessor_is_done(self):
        """Walk the workflow, checking the next-but-one is refused each time."""
        config = BoutiqueSettings.objects.get(id=1).workflow_config
        for index, key in enumerate(SEQUENCE[:-2]):
            # Only assert the refusal when the stage in between is mandatory.
            # Where it is optional the jump is legitimate -- that is what
            # `optional` is for -- but the walk must still advance either way.
            if not workflow.is_optional(config, SEQUENCE[index + 1]):
                later = SEQUENCE[index + 2]
                with self.assertRaises(ValueError, msg=f'{later} should be refused'):
                    self.move(later)
            self.move(key, 'SKIPPED' if key == 'maggam_work' else 'COMPLETED')

    def test_a_successful_transition_writes_exactly_one_activity_event(self):
        before = OrderActivity.objects.filter(order=self.order).count()
        self.advance_to('fabric_confirmed')
        self.move('fabric_confirmed')
        after = OrderActivity.objects.filter(order=self.order).count()
        # created, measurements_completed, fabric_confirmed
        self.assertEqual(after - before, 3)


class IdempotencyTests(StateMachineTestBase):

    def test_repeating_a_completed_transition_changes_nothing_further(self):
        """Double-clicks, retried POSTs and stale tabs all land here."""
        self.advance_to('fabric_confirmed')
        self.move('fabric_confirmed')
        after_first = self.snapshot()
        self.assertGreater(after_first['reserved'], 0)

        for _ in range(3):
            self.move('fabric_confirmed')

        self.assertEqual(self.snapshot(), after_first,
                         'a retry must not reserve, log or message again')

    def test_repeating_stitching_completed_does_not_consume_twice(self):
        """The case that now costs real stock if it goes wrong."""
        self.advance_to('stitching_completed')
        self.move('stitching_completed')
        after_first = self.snapshot()
        self.assertEqual(after_first['stock'], Decimal('23.000'))

        self.move('stitching_completed')
        self.move('stitching_completed')

        self.assertEqual(self.snapshot(), after_first)
        self.assertEqual(
            StockMovement.objects.filter(
                order=self.order,
                movement_type=StockMovement.Type.CONSUMPTION).count(), 1)


class OwnerDropdownLiveRegressionTests(StateMachineTestBase):
    """The whole business risk, over HTTP, on one order.

    An owner picking 'Delivered' from the status dropdown must never cause the
    system to manufacture a completed production and quality-check history. The
    control advances one client-facing band; it does not walk an order from the
    beginning to wherever it was pointed.
    """

    def setUp(self):
        super().setUp()
        from rest_framework.authtoken.models import Token
        from rest_framework.test import APIClient
        token, _ = Token.objects.get_or_create(user=self.owner)
        self.api = APIClient()
        self.api.credentials(
            HTTP_AUTHORIZATION=f'Token {token.key}',
            HTTP_X_TENANT_ID=self.tenant.schema_name,
        )

    def set_status(self, value):
        from django.urls import reverse
        return self.api.patch(
            reverse('order-update-status', args=[self.order.id]),
            {'status': value}, format='json')

    def test_the_dropdown_cannot_manufacture_a_delivered_order(self):
        before = self.snapshot()

        # 1-3. Straight for the end, from the very beginning.
        response = self.set_status('Delivered')
        self.assertEqual(response.status_code, 400)
        self.assertIn('not completed', str(response.data))

        # 4. Nothing moved. Not the order, not the ledger, not the audit trail.
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(before['reserved'], Decimal('0.000'))
        self.assertEqual(before['movements'], 0)

        # 5. The legitimate route, one band at a time.
        for value in ['Received', 'Confirmed', 'Design & Creation']:
            self.assertEqual(self.set_status(value).status_code, 200,
                             f'{value} should be reachable in turn')

        # Confirming fabric happened along the way, so the cloth is committed.
        mid = self.snapshot()
        self.assertEqual(mid['stages']['fabric_confirmed'], 'COMPLETED')
        self.assertEqual(mid['stages']['stitching_completed'], 'COMPLETED')
        self.assertGreater(mid['movements'], 0, 'materials followed production')

        # 6. Quality check still cannot be jumped, even from here.
        refused = self.set_status('Ready for Dispatch')
        self.assertEqual(refused.status_code, 400)
        self.assertIn('Master Quality Check', str(refused.data))
        self.assertEqual(
            self.order.stages.get(stage_key='master_quality_check').status,
            'NOT_STARTED')

        # 7. And only once it has actually run does the rest open up.
        self.assertEqual(self.set_status('Quality Check').status_code, 200)
        self.assertEqual(
            self.order.stages.get(stage_key='master_quality_check').status,
            'COMPLETED')
        for value in ['Ready for Dispatch', 'Delivered']:
            self.assertEqual(self.set_status(value).status_code, 200)

        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, 'Delivered')
        # Every mandatory stage genuinely settled -- no gaps behind the claim.
        outstanding = list(
            self.order.stages.exclude(status__in=('COMPLETED', 'SKIPPED'))
            .values_list('stage_key', flat=True))
        self.assertEqual(outstanding, [], f'delivered with gaps: {outstanding}')


class AtomicityTests(StateMachineTestBase):

    def test_a_failing_side_effect_rolls_the_whole_transition_back(self):
        """State, stock and audit share one transaction, or the ledger lies.

        Now that confirming fabric reserves material, a transition that half
        succeeds would leave the order saying one thing and the store room
        another -- the exact class of drift this whole change set exists to
        end.
        """
        self.advance_to('fabric_confirmed')
        before = self.snapshot()

        with mock.patch(
            'apps.inventory.order_materials.sync_order_materials',
            side_effect=RuntimeError('reservation exploded'),
        ):
            with self.assertRaises(RuntimeError):
                self.move('fabric_confirmed')

        self.assertEqual(self.snapshot(), before,
                         'a failed side effect must take the stage back with it')

    def test_a_successful_transition_commits_state_stock_and_audit_together(self):
        self.advance_to('fabric_confirmed')
        before = self.snapshot()

        self.move('fabric_confirmed')

        after = self.snapshot()
        self.assertEqual(after['stages']['fabric_confirmed'], 'COMPLETED')
        self.assertEqual(after['reserved'], Decimal('2.000'))
        self.assertEqual(after['activities'], before['activities'] + 1)
        self.assertEqual(after['stock'], before['stock'], 'reserving deducts nothing')
