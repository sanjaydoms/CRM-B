"""Alteration material consumption, and its distance from the original order."""

from decimal import Decimal

from apps.alterations.models import AlterationMaterialLine, AlterationType
from apps.alterations.testbase import AlterationTestCase
from apps.inventory.models import StockMovement
from domains.alterations import services


class AlterationMaterialTests(AlterationTestCase):

    def setUp(self):
        super().setUp()
        self.alteration = services.create_alteration_request(
            customer_id=self.customer.id, order_id=self.order.order_id,
            garment_job_id=self.blouse.id,
            alteration_type=AlterationType.PAID_CLIENT_REQUEST,
            issue_description='Needs a new panel.', charge_amount=Decimal('900.00'),
            performed_by=self.owner, role='Owner')

    def consume(self, item, quantity, **kw):
        return services.record_alteration_material_usage(
            self.alteration.id, item_id=item.id, quantity=Decimal(str(quantity)),
            recorded_by=self.owner, role='Owner', **kw)

    def test_consumption_moves_real_stock(self):
        before = self.fabric.current_stock
        line = self.consume(self.fabric, 2)
        self.fabric.refresh_from_db()

        self.assertEqual(self.fabric.current_stock, before - Decimal('2'))
        self.assertEqual(line.material_name, 'Silk Panel')
        self.assertIsNotNone(line.stock_movement)
        self.assertEqual(line.stock_movement.movement_type,
                         StockMovement.Type.CONSUMPTION)

    def test_the_movement_is_not_filed_against_the_original_order(self):
        """The delivered order's material history must not grow months later."""
        line = self.consume(self.fabric, 1)
        movement = line.stock_movement

        self.assertIsNone(movement.order_id)
        self.assertIsNone(movement.garment_job_id)
        self.assertIn(self.alteration.alteration_number, movement.remarks)
        self.assertEqual(self.order.stock_movements.count(), 0)

    def test_insufficient_stock_is_refused_and_changes_nothing(self):
        before = self.thread.current_stock
        with self.assertRaises(ValueError) as ctx:
            self.consume(self.thread, 999)
        self.assertIn('not enough', str(ctx.exception))

        self.thread.refresh_from_db()
        self.assertEqual(self.thread.current_stock, before)
        self.assertEqual(self.alteration.material_lines.count(), 0)

    def test_zero_and_negative_quantities_are_refused(self):
        for quantity in (0, -3):
            with self.assertRaises(ValueError):
                self.consume(self.fabric, quantity)

    def test_an_immediate_identical_repeat_is_refused(self):
        self.consume(self.fabric, 2)
        with self.assertRaises(ValueError) as ctx:
            self.consume(self.fabric, 2)
        self.assertIn('just recorded', str(ctx.exception))
        self.assertEqual(self.alteration.material_lines.count(), 1)

    def test_a_different_quantity_of_the_same_item_is_allowed(self):
        self.consume(self.fabric, 2)
        self.consume(self.fabric, 3)
        self.assertEqual(self.alteration.material_lines.count(), 2)

    def test_unknown_item_is_refused(self):
        import uuid
        with self.assertRaises(ValueError) as ctx:
            services.record_alteration_material_usage(
                self.alteration.id, item_id=uuid.uuid4(), quantity=Decimal('1'),
                recorded_by=self.owner, role='Owner')
        self.assertIn('could not be found', str(ctx.exception))

    def test_no_consumption_once_cancelled(self):
        services.cancel_alteration(self.alteration.id, reason='Withdrawn.',
                                   performed_by=self.owner, role='Owner')
        before = self.fabric.current_stock
        with self.assertRaises(ValueError) as ctx:
            self.consume(self.fabric, 1)
        self.assertIn('cancelled', str(ctx.exception))
        self.fabric.refresh_from_db()
        self.assertEqual(self.fabric.current_stock, before)

    def test_no_consumption_once_completed(self):
        for fn, kw in (
            (services.start_inspection, {}),
            (services.submit_for_approval, {}),
            (services.approve_alteration, {}),
            (services.assign_alteration, {'tailor_id': self.tailor.id}),
            (services.start_alteration_work, {}),
            (services.send_to_qc, {}),
            (services.pass_quality_check, {}),
        ):
            fn(self.alteration.id, performed_by=self.owner, role='Owner', **kw)
        services.record_alteration_payment(self.alteration.id, amount=Decimal('900.00'),
                                           received_by=self.owner, role='Owner')
        services.complete_alteration(self.alteration.id, performed_by=self.owner,
                                     role='Owner')

        with self.assertRaises(ValueError) as ctx:
            self.consume(self.fabric, 1)
        self.assertIn('completed', str(ctx.exception))

    def test_consumption_is_audited(self):
        self.consume(self.fabric, 2, remarks='Replacement side panel')
        activity = self.alteration.activities.get(event_type='MATERIAL_CONSUMED')
        self.assertEqual(activity.metadata['material_name'], 'Silk Panel')
        self.assertEqual(activity.metadata['quantity'], '2')

    def test_a_rollback_leaves_neither_stock_nor_a_line_behind(self):
        """The line and the movement live or die together."""
        before = self.fabric.current_stock
        movements_before = StockMovement.objects.count()

        from unittest.mock import patch
        with patch.object(AlterationMaterialLine.objects, 'create',
                          side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                self.consume(self.fabric, 2)

        self.fabric.refresh_from_db()
        self.assertEqual(self.fabric.current_stock, before)
        self.assertEqual(StockMovement.objects.count(), movements_before)
        self.assertEqual(self.alteration.material_lines.count(), 0)

    def test_only_the_owner_may_consume_stock(self):
        """Not a special rule: inventory is Owner-only everywhere in this product."""
        with self.assertRaises(PermissionError):
            services.record_alteration_material_usage(
                self.alteration.id, item_id=self.fabric.id, quantity=Decimal('1'),
                recorded_by=self.master.user, role='Master')
