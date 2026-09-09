"""Money on an alteration: its own ledger, and its own guard rails."""

from decimal import Decimal

from apps.alterations.models import (
    AlterationPayment,
    AlterationStatus,
    AlterationType,
    PaymentMethod,
    PaymentStatus,
)
from apps.alterations.testbase import AlterationTestCase
from domains.alterations import services


class AlterationPaymentTests(AlterationTestCase):

    def setUp(self):
        super().setUp()
        self.paid = self.new_alteration(AlterationType.PAID_CLIENT_REQUEST,
                                        Decimal('1000.00'), self.blouse)
        self.free = self.new_alteration(AlterationType.FREE_BOUTIQUE_FAULT,
                                        Decimal('0.00'), self.lehenga)

    def new_alteration(self, kind, charge, garment):
        return services.create_alteration_request(
            customer_id=self.customer.id, order_id=self.order.order_id,
            garment_job_id=garment.id, alteration_type=kind,
            issue_description='Fitting is not right.', charge_amount=charge,
            performed_by=self.owner, role='Owner')

    def pay(self, alteration, amount, **kw):
        return services.record_alteration_payment(
            alteration.id, amount=Decimal(str(amount)),
            received_by=self.owner, role='Owner', **kw)

    def ready_for_pickup(self, alteration):
        for fn, kw in (
            (services.start_inspection, {}),
            (services.submit_for_approval, {}),
            (services.approve_alteration, {}),
            (services.assign_alteration, {'tailor_id': self.tailor.id}),
            (services.start_alteration_work, {}),
            (services.send_to_qc, {}),
            (services.pass_quality_check, {}),
        ):
            fn(alteration.id, performed_by=self.owner, role='Owner', **kw)
        alteration.refresh_from_db()
        return alteration

    # -- the two types ----------------------------------------------------

    def test_free_alteration_owes_nothing_and_refuses_payment(self):
        self.assertEqual(services.calculate_outstanding_balance(self.free),
                         Decimal('0.00'))
        with self.assertRaises(ValueError) as ctx:
            self.pay(self.free, 100)
        self.assertIn('not chargeable', str(ctx.exception))

    def test_paid_alteration_owes_its_charge(self):
        self.assertEqual(services.calculate_outstanding_balance(self.paid),
                         Decimal('1000.00'))

    def test_charge_must_be_set_before_a_payment(self):
        unpriced = self.new_alteration(AlterationType.PAID_CLIENT_REQUEST,
                                       Decimal('0.00'), self.blouse)
        with self.assertRaises(ValueError) as ctx:
            self.pay(unpriced, 100)
        self.assertIn('No charge has been set', str(ctx.exception))

    # -- partial, full, over ----------------------------------------------

    def test_partial_then_full_payment(self):
        self.pay(self.paid, 400)
        self.paid.refresh_from_db()
        self.assertEqual(self.paid.amount_paid, Decimal('400.00'))
        self.assertEqual(services.calculate_outstanding_balance(self.paid),
                         Decimal('600.00'))

        self.pay(self.paid, 600, transaction_reference='UPI-2')
        self.paid.refresh_from_db()
        self.assertEqual(self.paid.amount_paid, Decimal('1000.00'))
        self.assertEqual(services.calculate_outstanding_balance(self.paid),
                         Decimal('0.00'))
        self.assertEqual(self.paid.payments.count(), 2)

    def test_overpayment_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            self.pay(self.paid, 1500)
        self.assertIn('more than the', str(ctx.exception))
        self.paid.refresh_from_db()
        self.assertEqual(self.paid.amount_paid, Decimal('0.00'))

    def test_overpayment_after_a_partial_is_refused(self):
        self.pay(self.paid, 700)
        with self.assertRaises(ValueError):
            self.pay(self.paid, 400, transaction_reference='UPI-X')
        self.paid.refresh_from_db()
        self.assertEqual(self.paid.amount_paid, Decimal('700.00'))

    def test_zero_and_negative_are_refused(self):
        for amount in (0, -50):
            with self.assertRaises(ValueError):
                self.pay(self.paid, amount)

    # -- duplicates -------------------------------------------------------

    def test_repeat_transaction_reference_is_refused(self):
        self.pay(self.paid, 200, transaction_reference='UPI-777')
        with self.assertRaises(ValueError) as ctx:
            self.pay(self.paid, 200, transaction_reference='UPI-777')
        self.assertIn('already been recorded', str(ctx.exception))
        self.paid.refresh_from_db()
        self.assertEqual(self.paid.amount_paid, Decimal('200.00'))

    def test_immediate_identical_repeat_without_a_reference_is_refused(self):
        self.pay(self.paid, 200)
        with self.assertRaises(ValueError) as ctx:
            self.pay(self.paid, 200)
        self.assertIn('identical payment', str(ctx.exception))

    def test_the_same_reference_on_a_different_alteration_is_fine(self):
        other = self.new_alteration(AlterationType.PAID_CLIENT_REQUEST,
                                    Decimal('300.00'), self.blouse)
        self.pay(self.paid, 100, transaction_reference='CASH-1')
        self.pay(other, 100, transaction_reference='CASH-1')
        self.assertEqual(
            AlterationPayment.objects.filter(transaction_reference='CASH-1').count(), 2)

    def test_a_genuine_second_payment_of_the_same_amount_needs_a_reference(self):
        self.pay(self.paid, 200)
        payment = self.pay(self.paid, 200, transaction_reference='UPI-SECOND')
        self.assertEqual(payment.status, PaymentStatus.COMPLETED)
        self.paid.refresh_from_db()
        self.assertEqual(self.paid.amount_paid, Decimal('400.00'))

    # -- state guards -----------------------------------------------------

    def test_no_payment_on_a_cancelled_alteration(self):
        services.cancel_alteration(self.paid.id, reason='Withdrawn.',
                                   performed_by=self.owner, role='Owner')
        with self.assertRaises(ValueError) as ctx:
            self.pay(self.paid, 100)
        self.assertIn('cancelled', str(ctx.exception))

    def test_no_payment_on_a_completed_alteration(self):
        self.ready_for_pickup(self.paid)
        self.pay(self.paid, 1000)
        services.complete_alteration(self.paid.id, performed_by=self.owner, role='Owner')
        with self.assertRaises(ValueError) as ctx:
            self.pay(self.paid, 50)
        self.assertIn('completed', str(ctx.exception))

    def test_invalid_payment_method_is_refused(self):
        with self.assertRaises(ValueError):
            self.pay(self.paid, 100, payment_method='BITCOIN')

    # -- completion gate --------------------------------------------------

    def test_paid_alteration_cannot_complete_while_money_is_owed(self):
        self.ready_for_pickup(self.paid)
        self.pay(self.paid, 400)
        with self.assertRaises(ValueError) as ctx:
            services.complete_alteration(self.paid.id, performed_by=self.owner,
                                         role='Owner')
        self.assertIn('outstanding balance', str(ctx.exception))
        self.paid.refresh_from_db()
        self.assertEqual(self.paid.status, AlterationStatus.READY_FOR_PICKUP)

    def test_free_alteration_completes_without_any_payment(self):
        self.ready_for_pickup(self.free)
        alteration = services.complete_alteration(
            self.free.id, performed_by=self.owner, role='Owner')
        self.assertEqual(alteration.status, AlterationStatus.COMPLETED)

    # -- bookkeeping ------------------------------------------------------

    def test_payment_records_who_took_it_and_how(self):
        payment = self.pay(self.paid, 250, payment_method=PaymentMethod.UPI,
                           transaction_reference='UPI-ABC', notes='At the counter')
        self.assertEqual(payment.payment_method, PaymentMethod.UPI)
        self.assertEqual(payment.received_by, self.owner)
        self.assertEqual(payment.received_by_name, self.owner.username)
        self.assertIsNotNone(payment.received_at)

    def test_payment_is_audited_with_the_running_balance(self):
        self.pay(self.paid, 250)
        activity = self.paid.activities.get(event_type='PAYMENT_RECEIVED')
        self.assertEqual(activity.metadata['amount'], '250.00')
        self.assertEqual(activity.metadata['outstanding_balance'], '750.00')

    def test_charge_cannot_be_cut_below_what_is_already_paid(self):
        self.pay(self.paid, 600)
        services.start_inspection(self.paid.id, performed_by=self.owner, role='Owner')
        with self.assertRaises(ValueError) as ctx:
            services.submit_for_approval(self.paid.id, charge_amount=Decimal('100.00'),
                                         performed_by=self.owner, role='Owner')
        self.assertIn('already paid', str(ctx.exception))
