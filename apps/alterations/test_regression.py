"""The whole point of the feature: the delivered order is history.

A full alteration lifecycle runs against a delivered order -- inspection,
approval, assignment, work, materials, QC failure, rework, QC pass, payment,
completion -- and then every field, row and total belonging to that order is
compared against a snapshot taken before any of it happened.
"""

from decimal import Decimal

from django.forms.models import model_to_dict

from apps.alterations.models import AlterationStatus, AlterationType
from apps.alterations.testbase import AlterationTestCase
from apps.production.models import ProductionTask, QCRecord
from crm_api.models import Order, OrderActivity, OrderStage, OrderStageHistory
from domains.alterations import services


class OriginalOrderIsUntouchedTests(AlterationTestCase):

    def snapshot(self):
        order = Order.objects.get(pk=self.order.pk)
        return {
            'order': model_to_dict(order),
            'stages': sorted(
                (model_to_dict(s) for s in OrderStage.objects.filter(order=order)),
                key=lambda row: row['sequence']),
            'stage_histories': [
                model_to_dict(h) for h in
                OrderStageHistory.objects.filter(order=order).order_by('id')],
            'garment_jobs': sorted(
                (model_to_dict(g) for g in order.garment_jobs.all()),
                key=lambda row: row['sequence']),
            'order_activities': OrderActivity.objects.filter(order=order).count(),
            'production_tasks': ProductionTask.objects.filter(order=order).count(),
            'qc_records': QCRecord.objects.filter(order=order).count(),
            'stock_movements': order.stock_movements.count(),
        }

    def run_full_lifecycle(self):
        alteration = services.create_alteration_request(
            customer_id=self.customer.id, order_id=self.order.order_id,
            garment_job_id=self.blouse.id,
            alteration_type=AlterationType.PAID_CLIENT_REQUEST,
            issue_description='The waist is loose.',
            requested_adjustments={'waist': 'let out 1 inch'},
            charge_amount=Decimal('1200.00'), performed_by=self.owner, role='Owner')

        step = lambda fn, **kw: fn(alteration.id, performed_by=self.owner,
                                   role='Owner', **kw)

        step(services.start_inspection)
        services.record_inspection(alteration.id, inspection_notes='Out by an inch.',
                                   adjustments={'waist': '+1'},
                                   performed_by=self.owner, role='Owner')
        step(services.submit_for_approval, charge_amount=Decimal('1200.00'))
        step(services.approve_alteration)
        step(services.assign_alteration, tailor_id=self.other_tailor.id)
        step(services.start_alteration_work)

        services.record_alteration_material_usage(
            alteration.id, item_id=self.fabric.id, quantity=Decimal('1.5'),
            recorded_by=self.owner, role='Owner', remarks='Waist panel')

        step(services.send_to_qc)
        step(services.fail_quality_check, reason='Seam puckered.')
        step(services.send_to_qc)
        step(services.pass_quality_check)

        services.record_alteration_payment(
            alteration.id, amount=Decimal('600.00'), received_by=self.owner,
            role='Owner', transaction_reference='UPI-A')
        services.record_alteration_payment(
            alteration.id, amount=Decimal('600.00'), received_by=self.owner,
            role='Owner', transaction_reference='UPI-B')

        step(services.complete_alteration)
        alteration.refresh_from_db()
        return alteration

    def test_a_complete_alteration_changes_nothing_about_the_order(self):
        before = self.snapshot()
        alteration = self.run_full_lifecycle()
        after = self.snapshot()

        self.assertEqual(alteration.status, AlterationStatus.COMPLETED)
        self.assertEqual(before, after)

    def test_the_order_is_still_delivered(self):
        self.run_full_lifecycle()
        order = Order.objects.get(pk=self.order.pk)
        self.assertEqual(order.order_status, 'Delivered')
        self.assertEqual(order.production_status, 'COMPLETED')
        self.assertEqual(order.current_stage_key, 'delivered')

    def test_the_orders_money_is_untouched(self):
        self.run_full_lifecycle()
        order = Order.objects.get(pk=self.order.pk)
        self.assertEqual(order.total_amount, Decimal('25000.00'))
        self.assertEqual(order.amount_paid, Decimal('25000.00'))
        self.assertEqual(order.payment_status, 'Paid')
        # The alteration's 1200 lives entirely on its own ledger.
        self.assertEqual(
            sum(p.amount for p in
                self.order.alteration_requests.get().payments.all()),
            Decimal('1200.00'))

    def test_every_production_stage_is_still_completed(self):
        self.run_full_lifecycle()
        statuses = set(OrderStage.objects.filter(order=self.order)
                       .values_list('status', flat=True))
        self.assertEqual(statuses, {'COMPLETED'})

    def test_the_garment_job_is_untouched(self):
        spec_before = dict(self.blouse.spec)
        price_before = self.blouse.base_price
        self.run_full_lifecycle()
        self.blouse.refresh_from_db()
        self.assertEqual(self.blouse.spec, spec_before)
        self.assertEqual(self.blouse.base_price, price_before)

    def test_no_production_task_or_qc_record_is_created(self):
        self.run_full_lifecycle()
        self.assertEqual(ProductionTask.objects.count(), 0)
        self.assertEqual(QCRecord.objects.count(), 0)

    def test_the_orders_inventory_history_does_not_grow(self):
        self.run_full_lifecycle()
        self.assertEqual(self.order.stock_movements.count(), 0)
        # ...even though stock genuinely moved.
        self.fabric.refresh_from_db()
        self.assertEqual(self.fabric.current_stock, Decimal('18.500'))

    def test_a_cancelled_alteration_also_leaves_the_order_alone(self):
        before = self.snapshot()
        alteration = services.create_alteration_request(
            customer_id=self.customer.id, order_id=self.order.order_id,
            garment_job_id=self.lehenga.id,
            alteration_type=AlterationType.FREE_BOUTIQUE_FAULT,
            issue_description='Hem uneven.', performed_by=self.owner, role='Owner')
        services.start_inspection(alteration.id, performed_by=self.owner, role='Owner')
        services.cancel_alteration(alteration.id, reason='Customer withdrew.',
                                   performed_by=self.owner, role='Owner')
        self.assertEqual(before, self.snapshot())
