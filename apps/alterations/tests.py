"""Model, workflow and service-level tests for post-delivery alterations."""

from decimal import Decimal

from django.db.utils import IntegrityError

from apps.alterations.models import (
    AlterationActivity,
    AlterationRequest,
    AlterationStatus,
    AlterationTask,
    AlterationTaskStatus,
    AlterationType,
)
from apps.alterations.testbase import AlterationTestCase
from domains.alterations import services
from domains.alterations.workflow import (
    ALLOWED_TRANSITIONS,
    TransitionError,
    available_actions,
    validate_transition,
)


class IntakeTests(AlterationTestCase):

    def make(self, **kw):
        params = dict(
            customer_id=self.customer.id,
            order_id=self.order.order_id,
            garment_job_id=self.blouse.id,
            alteration_type=AlterationType.PAID_CLIENT_REQUEST,
            issue_description='The waist is loose.',
            charge_amount=Decimal('500.00'),
            performed_by=self.owner, role='Owner',
        )
        params.update(kw)
        return services.create_alteration_request(**params)

    def test_delivered_order_can_take_an_alteration(self):
        alteration = self.make()
        self.assertEqual(alteration.status, AlterationStatus.RECEIVED)
        self.assertEqual(alteration.original_order_id, self.order.id)
        self.assertEqual(alteration.garment_job_id, self.blouse.id)
        self.assertTrue(alteration.alteration_number.startswith('ALT-T2B-ALT-1-'))

    def test_order_still_in_production_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            self.make(order_id=self.live_order.order_id,
                      garment_job_id=self.live_garment.id)
        self.assertIn('Delivered', str(ctx.exception))

    def test_garment_must_belong_to_the_order(self):
        stranger = self.live_order.garment_jobs.first()
        with self.assertRaises(ValueError) as ctx:
            self.make(garment_job_id=stranger.id)
        self.assertIn('does not belong', str(ctx.exception))

    def test_order_must_belong_to_the_customer(self):
        from crm_api.models import Customer
        other = Customer.objects.create(
            first_name='Priya', last_name='Nair', mobile_number='919845099999')
        with self.assertRaises(ValueError) as ctx:
            self.make(customer_id=other.id)
        self.assertIn('does not belong', str(ctx.exception))

    def test_free_alteration_cannot_carry_a_charge(self):
        with self.assertRaises(ValueError) as ctx:
            self.make(alteration_type=AlterationType.FREE_BOUTIQUE_FAULT,
                      charge_amount=Decimal('500.00'))
        self.assertIn('cannot carry a charge', str(ctx.exception))

    def test_intake_writes_an_audit_row(self):
        alteration = self.make()
        activity = alteration.activities.get(event_type='ALTERATION_CREATED')
        self.assertEqual(activity.to_status, AlterationStatus.RECEIVED)
        self.assertEqual(activity.performed_by_name, self.owner.username)

    def test_two_garments_from_one_order_get_distinct_numbers(self):
        first = self.make(garment_job_id=self.blouse.id)
        second = self.make(garment_job_id=self.lehenga.id)
        self.assertNotEqual(first.alteration_number, second.alteration_number)
        self.assertEqual(
            AlterationRequest.objects.filter(original_order=self.order).count(), 2)

    def test_several_alterations_against_the_same_garment_are_allowed(self):
        self.make()
        again = self.make(issue_description='And now the sleeves.')
        self.assertEqual(again.status, AlterationStatus.RECEIVED)

    def test_a_user_with_no_role_cannot_create(self):
        with self.assertRaises(PermissionError):
            self.make(performed_by=self.rogue, role=None)


class WorkflowTests(AlterationTestCase):

    def setUp(self):
        super().setUp()
        self.alteration = services.create_alteration_request(
            customer_id=self.customer.id, order_id=self.order.order_id,
            garment_job_id=self.blouse.id,
            alteration_type=AlterationType.PAID_CLIENT_REQUEST,
            issue_description='Waist loose', charge_amount=Decimal('800.00'),
            performed_by=self.owner, role='Owner')

    def owner_call(self, fn, **kw):
        return fn(self.alteration.id, performed_by=self.owner, role='Owner', **kw)

    def advance_to(self, target):
        """Walk the happy path up to (not including) `target`."""
        steps = [
            (AlterationStatus.INSPECTION, lambda: self.owner_call(services.start_inspection)),
            (AlterationStatus.PENDING_APPROVAL,
             lambda: self.owner_call(services.submit_for_approval)),
            (AlterationStatus.APPROVED, lambda: self.owner_call(services.approve_alteration)),
            (AlterationStatus.ASSIGNED,
             lambda: self.owner_call(services.assign_alteration, tailor_id=self.tailor.id)),
            (AlterationStatus.IN_PROGRESS,
             lambda: self.owner_call(services.start_alteration_work)),
            (AlterationStatus.QC, lambda: self.owner_call(services.send_to_qc)),
            (AlterationStatus.READY_FOR_PICKUP,
             lambda: self.owner_call(services.pass_quality_check)),
        ]
        for reached, step in steps:
            if reached == target:
                return
            step()

    def test_full_happy_path(self):
        self.advance_to(AlterationStatus.COMPLETED)
        self.alteration.refresh_from_db()
        self.assertEqual(self.alteration.status, AlterationStatus.READY_FOR_PICKUP)

        services.record_alteration_payment(
            self.alteration.id, amount=Decimal('800.00'),
            received_by=self.owner, role='Owner')
        alteration = self.owner_call(services.complete_alteration)

        self.assertEqual(alteration.status, AlterationStatus.COMPLETED)
        self.assertIsNotNone(alteration.completed_at)

    def test_inspection_cannot_be_skipped(self):
        with self.assertRaises(TransitionError):
            self.owner_call(services.submit_for_approval)

    def test_work_cannot_start_before_approval(self):
        self.owner_call(services.start_inspection)
        self.owner_call(services.submit_for_approval)
        with self.assertRaises(TransitionError):
            self.owner_call(services.start_alteration_work)

    def test_qc_failure_returns_to_in_progress_and_needs_a_reason(self):
        self.advance_to(AlterationStatus.READY_FOR_PICKUP)
        self.alteration.refresh_from_db()
        self.assertEqual(self.alteration.status, AlterationStatus.QC)

        with self.assertRaises(ValueError):
            self.owner_call(services.fail_quality_check, reason='   ')

        alteration = self.owner_call(services.fail_quality_check,
                                     reason='Hem is uneven on the left.')
        self.assertEqual(alteration.status, AlterationStatus.IN_PROGRESS)
        self.assertEqual(
            alteration.activities.get(event_type='QC_FAILED').metadata['reason'],
            'Hem is uneven on the left.')

        # And round again.
        self.owner_call(services.send_to_qc)
        alteration = self.owner_call(services.pass_quality_check)
        self.assertEqual(alteration.status, AlterationStatus.READY_FOR_PICKUP)

    def test_qc_failure_only_from_qc(self):
        self.advance_to(AlterationStatus.IN_PROGRESS)
        with self.assertRaises(TransitionError):
            self.owner_call(services.fail_quality_check, reason='too early')

    def test_cancellation_requires_a_reason_and_stops_the_tasks(self):
        self.advance_to(AlterationStatus.IN_PROGRESS)
        with self.assertRaises(ValueError):
            self.owner_call(services.cancel_alteration, reason='')

        alteration = self.owner_call(services.cancel_alteration,
                                     reason='Customer changed their mind.')
        self.assertEqual(alteration.status, AlterationStatus.CANCELLED)
        self.assertIsNotNone(alteration.cancelled_at)
        self.assertTrue(all(t.status == AlterationTaskStatus.CANCELLED
                            for t in alteration.tasks.all()))

    def test_terminal_states_are_terminal(self):
        self.advance_to(AlterationStatus.IN_PROGRESS)
        self.owner_call(services.cancel_alteration, reason='Withdrawn.')
        for fn in (services.start_inspection, services.approve_alteration,
                   services.complete_alteration):
            with self.assertRaises(TransitionError):
                self.owner_call(fn)

    def test_completed_cannot_be_cancelled(self):
        self.advance_to(AlterationStatus.COMPLETED)
        services.record_alteration_payment(
            self.alteration.id, amount=Decimal('800.00'),
            received_by=self.owner, role='Owner')
        self.owner_call(services.complete_alteration)
        with self.assertRaises(TransitionError):
            self.owner_call(services.cancel_alteration, reason='Too late.')

    def test_assignment_creates_a_task_and_reassignment_reuses_it(self):
        self.advance_to(AlterationStatus.ASSIGNED)
        self.owner_call(services.assign_alteration, tailor_id=self.tailor.id)
        self.assertEqual(self.alteration.tasks.count(), 1)

        task = self.alteration.tasks.get()
        self.assertEqual(task.assigned_to_id, self.tailor.id)
        self.assertEqual(task.status, AlterationTaskStatus.PENDING)

    def test_work_can_be_handed_to_a_different_tailor_before_it_starts(self):
        self.advance_to(AlterationStatus.ASSIGNED)
        self.owner_call(services.assign_alteration, tailor_id=self.tailor.id)
        self.owner_call(services.assign_alteration, tailor_id=self.other_tailor.id)

        self.assertEqual(self.alteration.tasks.count(), 1)
        self.assertEqual(self.alteration.tasks.get().assigned_to_id, self.other_tailor.id)
        self.alteration.refresh_from_db()
        self.assertEqual(self.alteration.status, AlterationStatus.ASSIGNED)

    def test_one_task_per_stage_is_enforced_by_the_database(self):
        self.advance_to(AlterationStatus.ASSIGNED)
        self.owner_call(services.assign_alteration, tailor_id=self.tailor.id)
        with self.assertRaises(IntegrityError):
            AlterationTask.objects.create(
                alteration_request=self.alteration, stage_key='alteration_work',
                title='Duplicate')

    def test_work_timestamps_are_recorded(self):
        self.advance_to(AlterationStatus.IN_PROGRESS)
        self.owner_call(services.start_alteration_work)
        task = self.alteration.tasks.get()
        self.assertIsNotNone(task.started_at)
        self.assertEqual(task.status, AlterationTaskStatus.IN_PROGRESS)

        self.owner_call(services.send_to_qc)
        task.refresh_from_db()
        self.assertIsNotNone(task.completed_at)
        self.assertEqual(task.status, AlterationTaskStatus.COMPLETED)

    def test_inspection_findings_are_stored_without_touching_the_garment_spec(self):
        self.owner_call(services.start_inspection)
        original_spec = dict(self.blouse.spec)
        services.record_inspection(
            self.alteration.id, inspection_notes='Waist out by 1 inch.',
            adjustments={'waist': '+1 inch'}, performed_by=self.owner, role='Owner')

        self.alteration.refresh_from_db()
        self.blouse.refresh_from_db()
        self.assertEqual(self.alteration.inspection_adjustments, {'waist': '+1 inch'})
        self.assertEqual(self.blouse.spec, original_spec)

    def test_inspection_findings_only_during_inspection(self):
        with self.assertRaises(TransitionError):
            services.record_inspection(self.alteration.id, inspection_notes='x',
                                       performed_by=self.owner, role='Owner')

    def test_every_transition_is_audited(self):
        self.advance_to(AlterationStatus.COMPLETED)
        services.record_alteration_payment(
            self.alteration.id, amount=Decimal('800.00'),
            received_by=self.owner, role='Owner')
        self.owner_call(services.complete_alteration)

        events = set(AlterationActivity.objects
                     .filter(alteration_request=self.alteration)
                     .values_list('event_type', flat=True))
        self.assertEqual(events, {
            'ALTERATION_CREATED', 'INSPECTION_STARTED', 'SUBMITTED_FOR_APPROVAL',
            'ALTERATION_APPROVED', 'ALTERATION_ASSIGNED', 'WORK_STARTED',
            'SENT_TO_QC', 'QC_PASSED', 'PAYMENT_RECEIVED', 'ALTERATION_COMPLETED',
        })

    def test_available_actions_track_the_state_machine(self):
        self.assertIn('start-inspection', available_actions(self.alteration, 'Owner'))
        self.assertNotIn('approve', available_actions(self.alteration, 'Owner'))

        self.advance_to(AlterationStatus.APPROVED)
        self.alteration.refresh_from_db()
        actions = available_actions(self.alteration, 'Owner')
        self.assertIn('approve', actions)
        self.assertNotIn('start-inspection', actions)

    def test_transition_table_has_no_route_out_of_a_terminal_state(self):
        self.assertEqual(ALLOWED_TRANSITIONS[AlterationStatus.COMPLETED], set())
        self.assertEqual(ALLOWED_TRANSITIONS[AlterationStatus.CANCELLED], set())

    def test_unknown_status_is_rejected(self):
        with self.assertRaises(TransitionError):
            validate_transition('NONSENSE', AlterationStatus.INSPECTION)
