"""Payroll: the arithmetic, the locks, and who may see a wage.

Three groups of test matter more than the rest and are worth naming:

  * `GrossCalculationTests` -- the money. Rounding once, at the end, in Decimal.
  * `RateSnapshotTests` -- an approved week must not move when a rate changes.
  * `PayrollAccessTests` / `CrossTenantPayrollTests` -- who can read a wage.

Everything else guards a way those three could be got at sideways.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import IntegrityError, connection, transaction
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.activities.models import UniversalActivity
from apps.staff.models import AttendanceSession, StaffProfile
from core.formatting import tenant_timezone
from crm_api.models import Customer, Order, Tailor
from tenants.models import BoutiqueTenant

from . import deposits, services
from .models import PayrollPeriod, PayrollRecord, StaffLedgerEntry

#: Monday 31 August 2026. Every fixture week in this file starts here.
MONDAY = date(2026, 8, 31)


class PayrollTestCase(TenantTestCase):
    """A boutique, an owner, and staff who are paid different amounts."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = 'owner@payroll.test'
        tenant.name = 'Payroll Atelier'
        tenant.timezone = 'Asia/Kolkata'
        return tenant

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        self.owner = User.objects.create_user(
            username='owner@payroll.test', email='owner@payroll.test',
            password='ownerpass12345')
        self.anita, self.anita_user = self._staff('Anita', 'anita@payroll.test', 'Tailor')
        self.balan, self.balan_user = self._staff('Balan', 'balan@payroll.test', 'Tailor')

    def _staff(self, name, email, role):
        user = User.objects.create_user(
            username=email, email=email, password='staffpass12345')
        tailor = Tailor.objects.create(
            name=name, specialty='Stitching', role=role, email=email, user=user)
        return tailor, user

    def profile(self, tailor, rate='100.00', **extra):
        return StaffProfile.objects.create(
            staff=tailor, hourly_rate=Decimal(rate), **extra)

    def at(self, day, hour, minute=0, month=8, year=2026):
        return datetime(year, month, day, hour, minute, tzinfo=tenant_timezone())

    def session(self, tailor, day, start_hour, end_hour, month=9, minutes=None,
                start_minute=0, end_minute=0):
        """A completed attendance session, with minutes stored as the app does."""
        check_in = self.at(day, start_hour, start_minute, month=month)
        check_out = self.at(day, end_hour, end_minute, month=month)
        s = AttendanceSession(
            staff=tailor, date=date(2026, month, day),
            check_in=check_in, check_out=check_out)
        s.minutes = minutes if minutes is not None else s.duration_minutes()
        s.save()
        return s

    def client_for(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Token {token.key}',
                        HTTP_X_TENANT_ID=self.tenant.schema_name)
        return api

    def generate(self, day=MONDAY):
        return services.generate(day, user=self.owner)


class GrossCalculationTests(PayrollTestCase):
    """Minutes into rupees. The one calculation everything else protects."""

    def test_an_exact_hour(self):
        self.assertEqual(services.gross_for(60, Decimal('100.00')), Decimal('100.00'))

    def test_half_an_hour(self):
        self.assertEqual(services.gross_for(30, Decimal('100.00')), Decimal('50.00'))

    def test_uneven_minutes_round_half_up_at_the_end(self):
        """25 minutes at Rs.100 is 41.6666..., which becomes 41.67."""
        self.assertEqual(services.gross_for(25, Decimal('100.00')), Decimal('41.67'))

    def test_rounding_happens_once_not_per_step(self):
        """Rounding hours first would give a different, wrong answer.

        25 minutes is 0.41666... hours. Quantising THAT to 0.42 and multiplying
        by 100 gives 42.00 -- eight paise adrift on one session, and compounding
        with every session in the week.
        """
        rounded_hours_first = (Decimal('25') / Decimal('60')).quantize(Decimal('0.01'))
        self.assertEqual(rounded_hours_first * Decimal('100'), Decimal('42.00'))
        self.assertEqual(services.gross_for(25, Decimal('100.00')), Decimal('41.67'))

    def test_a_full_working_week(self):
        """42h 30m at Rs.100 is Rs.4,250 -- the figure from the brief."""
        self.assertEqual(services.gross_for(2550, Decimal('100.00')),
                         Decimal('4250.00'))

    def test_zero_minutes_is_zero_rupees(self):
        self.assertEqual(services.gross_for(0, Decimal('100.00')), Decimal('0.00'))

    def test_a_missing_rate_is_not_zero_rupees(self):
        """None, never 0.00 -- a zero would be added to a total and approved."""
        self.assertIsNone(services.gross_for(480, None))

    def test_the_result_is_always_decimal(self):
        self.assertIsInstance(services.gross_for(37, Decimal('137.50')), Decimal)

    def test_an_awkward_rate_still_lands_on_two_places(self):
        # 37 minutes at 137.50 = 84.7916666...
        self.assertEqual(services.gross_for(37, Decimal('137.50')), Decimal('84.79'))


class PeriodBoundsTests(PayrollTestCase):
    def test_the_week_runs_monday_to_sunday(self):
        start, end = services.period_bounds(date(2026, 9, 2))  # a Wednesday
        self.assertEqual(start, MONDAY)
        self.assertEqual(end, date(2026, 9, 6))
        self.assertEqual(start.weekday(), 0)
        self.assertEqual(end.weekday(), 6)

    def test_a_monday_is_its_own_week_start(self):
        start, _ = services.period_bounds(MONDAY)
        self.assertEqual(start, MONDAY)

    def test_a_sunday_belongs_to_the_week_that_began_before_it(self):
        start, end = services.period_bounds(date(2026, 9, 6))
        self.assertEqual(start, MONDAY)
        self.assertEqual(end, date(2026, 9, 6))

    def test_payroll_and_the_timesheet_agree_on_the_week(self):
        """Two definitions of "the week" is how a timesheet and a payslip differ."""
        from apps.staff.attendance import week_start
        for day in (date(2026, 9, 1), date(2026, 9, 4), date(2026, 9, 6)):
            self.assertEqual(services.period_bounds(day)[0], week_start(day))


class GenerationTests(PayrollTestCase):
    def test_a_week_of_attendance_becomes_one_payroll_record(self):
        self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 17)   # 8h
        period = self.generate()
        record = period.records.get()
        self.assertEqual(record.worked_minutes, 480)
        self.assertEqual(record.gross_earnings, Decimal('800.00'))
        self.assertEqual(record.hourly_rate_snapshot, Decimal('100.00'))
        self.assertEqual(record.status, 'DRAFT')

    def test_several_sessions_add_up(self):
        self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 17)    # 480
        self.session(self.anita, 2, 10, 19)   # 540
        self.session(self.anita, 3, 9, 13)    # 240
        record = self.generate().records.get()
        self.assertEqual(record.worked_minutes, 1260)
        self.assertEqual(record.gross_earnings, Decimal('2100.00'))

    def test_an_overnight_session_is_paid_from_its_stored_minutes(self):
        """Attendance already resolved midnight; payroll just reads 480."""
        self.profile(self.anita, '100.00')
        s = AttendanceSession(
            staff=self.anita, date=date(2026, 9, 1),
            check_in=self.at(1, 23, month=9), check_out=self.at(2, 7, month=9))
        s.minutes = s.duration_minutes()
        s.save()
        self.assertEqual(s.minutes, 480)
        record = self.generate().records.get()
        self.assertEqual(record.worked_minutes, 480)
        self.assertEqual(record.gross_earnings, Decimal('800.00'))

    def test_each_staff_member_gets_their_own_record_at_their_own_rate(self):
        self.profile(self.anita, '100.00')
        self.profile(self.balan, '150.00')
        self.session(self.anita, 1, 9, 17)
        self.session(self.balan, 1, 9, 17)
        period = self.generate()
        by_name = {r.staff_name_snapshot: r for r in period.records.all()}
        self.assertEqual(by_name['Anita'].gross_earnings, Decimal('800.00'))
        self.assertEqual(by_name['Balan'].gross_earnings, Decimal('1200.00'))

    def test_attendance_from_another_week_is_not_included(self):
        self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 17)             # in week
        self.session(self.anita, 8, 9, 17, month=9)    # next week
        record = self.generate().records.get()
        self.assertEqual(record.worked_minutes, 480)

    def test_staff_with_no_attendance_get_no_record(self):
        """No zero-rupee rows for people who were not there."""
        self.profile(self.anita, '100.00')
        self.profile(self.balan, '100.00')
        self.session(self.anita, 1, 9, 17)
        period = self.generate()
        self.assertEqual(period.records.count(), 1)
        self.assertEqual(period.records.get().staff_name_snapshot, 'Anita')

    def test_staff_with_no_employment_profile_are_not_paid(self):
        self.session(self.anita, 1, 9, 17)  # attendance but no profile
        period = self.generate()
        self.assertEqual(period.records.count(), 0)

    def test_the_breakdown_records_where_the_minutes_came_from(self):
        self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 17)
        self.session(self.anita, 2, 10, 19)
        record = self.generate().records.get()
        self.assertEqual(len(record.session_breakdown), 2)
        self.assertEqual(sum(e['minutes'] for e in record.session_breakdown), 1020)
        self.assertIn('check_in', record.session_breakdown[0])

    def test_generation_is_logged(self):
        self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 17)
        self.client_for(self.owner).post(
            reverse('payroll-period-generate'), {'week': '2026-09-01'}, format='json')
        entry = UniversalActivity.objects.get(action='PAYROLL_GENERATED')
        self.assertEqual(entry.entity_type, 'PayrollPeriod')

    def test_the_activity_log_carries_no_individual_wage(self):
        """Owner and Master can both read the activity feed."""
        self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 17)
        self.client_for(self.owner).post(
            reverse('payroll-period-generate'), {'week': '2026-09-01'}, format='json')
        for entry in UniversalActivity.objects.all():
            blob = f"{entry.title} {entry.description} {entry.new_value} {entry.old_value}"
            self.assertNotIn('800.00', blob)
            self.assertNotIn('100.00', blob)


class IdempotentGenerationTests(PayrollTestCase):
    def test_generating_three_times_makes_one_period_and_one_record(self):
        self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 17)
        for _ in range(3):
            self.generate()
        self.assertEqual(PayrollPeriod.objects.count(), 1)
        self.assertEqual(PayrollRecord.objects.count(), 1)

    def test_the_database_refuses_a_second_period_for_one_week(self):
        self.generate()
        with self.assertRaises(IntegrityError):
            PayrollPeriod.objects.create(
                period_start=MONDAY, period_end=date(2026, 9, 6))

    def test_the_database_refuses_two_records_for_one_person_in_one_week(self):
        self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 17)
        period = self.generate()
        with self.assertRaises(IntegrityError):
            PayrollRecord.objects.create(
                period=period, staff=self.anita, staff_name_snapshot='Anita',
                worked_minutes=1, regular_minutes=1)

    def test_regenerating_picks_up_corrected_attendance(self):
        self.profile(self.anita, '100.00')
        s = self.session(self.anita, 1, 9, 17)   # 8h -> 800
        self.assertEqual(self.generate().records.get().gross_earnings,
                         Decimal('800.00'))
        s.check_out = self.at(1, 18, month=9)    # now 9h
        s.minutes = s.duration_minutes()
        s.save()
        self.assertEqual(self.generate().records.get().gross_earnings,
                         Decimal('900.00'))

    def test_regenerating_drops_someone_whose_attendance_was_removed(self):
        self.profile(self.anita, '100.00')
        s = self.session(self.anita, 1, 9, 17)
        self.assertEqual(self.generate().records.count(), 1)
        s.delete()
        self.assertEqual(self.generate().records.count(), 0)


class RateSnapshotTests(PayrollTestCase):
    """An approved week is a record of what was paid, not a live query."""

    def test_a_later_rate_change_does_not_move_an_approved_week(self):
        profile = self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 17)
        period = self.generate()
        services.approve(period, user=self.owner)

        profile.hourly_rate = Decimal('150.00')
        profile.save()

        record = PayrollRecord.objects.get()
        self.assertEqual(record.hourly_rate_snapshot, Decimal('100.00'))
        self.assertEqual(record.gross_earnings, Decimal('800.00'))

    def test_a_later_rate_change_does_not_move_an_approved_week_over_the_api(self):
        profile = self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 17)
        owner = self.client_for(self.owner)
        owner.post(reverse('payroll-period-generate'), {'week': '2026-09-01'},
                   format='json')
        period = PayrollPeriod.objects.get()
        owner.post(reverse('payroll-period-approve', args=[period.id]), {},
                   format='json')

        profile.hourly_rate = Decimal('150.00')
        profile.save()

        response = owner.get(reverse('payroll-period-detail', args=[period.id]))
        self.assertEqual(response.data['records'][0]['hourly_rate_snapshot'],
                         '100.00')
        self.assertEqual(response.data['records'][0]['gross_earnings'], '800.00')

    def test_the_next_week_uses_the_new_rate(self):
        profile = self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 17)
        services.approve(self.generate(), user=self.owner)

        profile.hourly_rate = Decimal('150.00')
        profile.save()
        self.session(self.anita, 8, 9, 17, month=9)
        later = self.generate(date(2026, 9, 8))
        self.assertEqual(later.records.get().hourly_rate_snapshot, Decimal('150.00'))
        self.assertEqual(later.records.get().gross_earnings, Decimal('1200.00'))

    def test_the_record_survives_the_staff_member_being_deleted(self):
        self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 17)
        services.approve(self.generate(), user=self.owner)
        self.anita.delete()
        record = PayrollRecord.objects.get()
        self.assertIsNone(record.staff)
        self.assertEqual(record.staff_name_snapshot, 'Anita')
        self.assertEqual(record.gross_earnings, Decimal('800.00'))

    def test_an_approved_record_explains_itself_after_attendance_is_corrected(self):
        self.profile(self.anita, '100.00')
        s = self.session(self.anita, 1, 9, 17)
        services.approve(self.generate(), user=self.owner)

        s.check_out = self.at(1, 23, month=9)
        s.minutes = s.duration_minutes()
        s.save()

        record = PayrollRecord.objects.get()
        self.assertEqual(record.worked_minutes, 480)
        self.assertEqual(record.session_breakdown[0]['minutes'], 480)


class MissingRateTests(PayrollTestCase):
    def test_a_worker_with_no_rate_is_flagged_not_paid_zero(self):
        self.profile(self.anita, '0.00')
        self.session(self.anita, 1, 9, 17)
        record = self.generate().records.get()
        self.assertIsNone(record.hourly_rate_snapshot)
        self.assertIsNone(record.gross_earnings)
        self.assertTrue(record.rate_missing)
        self.assertTrue(record.blocks_approval)

    def test_a_period_with_a_missing_rate_cannot_be_approved(self):
        self.profile(self.anita, '0.00')
        self.session(self.anita, 1, 9, 17)
        period = self.generate()
        with self.assertRaises(services.PayrollError) as caught:
            services.approve(period, user=self.owner)
        self.assertIn('Anita', str(caught.exception))
        period.refresh_from_db()
        self.assertEqual(period.status, 'DRAFT')

    def test_setting_the_rate_and_regenerating_unblocks_it(self):
        profile = self.profile(self.anita, '0.00')
        self.session(self.anita, 1, 9, 17)
        self.generate()
        profile.hourly_rate = Decimal('100.00')
        profile.save()
        period = self.generate()
        self.assertFalse(period.records.get().blocks_approval)
        services.approve(period, user=self.owner)
        period.refresh_from_db()
        self.assertEqual(period.status, 'APPROVED')

    def test_the_api_refuses_approval_with_a_missing_rate(self):
        self.profile(self.anita, '0.00')
        self.session(self.anita, 1, 9, 17)
        period = self.generate()
        response = self.client_for(self.owner).post(
            reverse('payroll-period-approve', args=[period.id]), {}, format='json')
        self.assertEqual(response.status_code, 409)
        self.assertIn('Anita', response.data['error'])


class OpenSessionTests(PayrollTestCase):
    def test_an_open_session_pays_nothing_and_is_reported(self):
        self.profile(self.anita, '100.00')
        AttendanceSession.objects.create(
            staff=self.anita, date=date(2026, 9, 1), check_in=self.at(1, 9, month=9))
        record = self.generate().records.get()
        self.assertEqual(record.worked_minutes, 0)
        self.assertEqual(record.gross_earnings, Decimal('0.00'))
        self.assertEqual(record.open_session_count, 1)

    def test_an_open_session_does_not_suppress_the_completed_ones(self):
        self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 17)
        AttendanceSession.objects.create(
            staff=self.anita, date=date(2026, 9, 2), check_in=self.at(2, 9, month=9))
        record = self.generate().records.get()
        self.assertEqual(record.worked_minutes, 480)
        self.assertEqual(record.open_session_count, 1)

    def test_no_checkout_time_is_invented(self):
        self.profile(self.anita, '100.00')
        session = AttendanceSession.objects.create(
            staff=self.anita, date=date(2026, 9, 1), check_in=self.at(1, 9, month=9))
        self.generate()
        session.refresh_from_db()
        self.assertIsNone(session.check_out)
        self.assertIsNone(session.minutes)

    def test_an_open_session_alone_does_not_block_approval(self):
        """It is a warning, not an error -- the week can still be signed off."""
        self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 17)
        AttendanceSession.objects.create(
            staff=self.anita, date=date(2026, 9, 2), check_in=self.at(2, 9, month=9))
        period = self.generate()
        services.approve(period, user=self.owner)
        period.refresh_from_db()
        self.assertEqual(period.status, 'APPROVED')


class OverlapTests(PayrollTestCase):
    def test_overlapping_completed_sessions_are_flagged(self):
        """Owner corrections can produce these; summing them pays an hour twice."""
        self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 13)    # 09:00-13:00
        self.session(self.anita, 1, 12, 17)   # 12:00-17:00, overlaps by an hour
        record = self.generate().records.get()
        self.assertTrue(record.has_overlap)
        self.assertTrue(record.blocks_approval)

    def test_an_overlap_blocks_approval_rather_than_double_paying(self):
        self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 13)
        self.session(self.anita, 1, 12, 17)
        period = self.generate()
        with self.assertRaises(services.PayrollError):
            services.approve(period, user=self.owner)

    def test_sessions_that_merely_touch_do_not_count_as_overlapping(self):
        self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 13)
        self.session(self.anita, 1, 13, 17)
        record = self.generate().records.get()
        self.assertFalse(record.has_overlap)
        self.assertEqual(record.worked_minutes, 480)


class EmploymentDateTests(PayrollTestCase):
    def test_attendance_before_the_joining_date_is_not_paid(self):
        self.profile(self.anita, '100.00', joined_at=date(2026, 9, 2))
        self.session(self.anita, 1, 9, 17)   # Tuesday, before joining
        self.session(self.anita, 3, 9, 17)   # Thursday, after joining
        record = self.generate().records.get()
        self.assertEqual(record.worked_minutes, 480)

    def test_attendance_after_the_exit_date_is_not_paid(self):
        self.profile(self.anita, '100.00', joined_at=date(2026, 1, 1),
                     exit_date=date(2026, 9, 2))
        self.session(self.anita, 1, 9, 17)
        self.session(self.anita, 4, 9, 17)   # after leaving
        record = self.generate().records.get()
        self.assertEqual(record.worked_minutes, 480)

    def test_someone_who_joins_after_the_week_gets_no_record(self):
        self.profile(self.anita, '100.00', joined_at=date(2026, 10, 1))
        self.session(self.anita, 1, 9, 17)
        self.assertEqual(self.generate().records.count(), 0)

    def test_someone_who_left_before_the_week_gets_no_record(self):
        self.profile(self.anita, '100.00', exit_date=date(2026, 1, 1))
        self.session(self.anita, 1, 9, 17)
        self.assertEqual(self.generate().records.count(), 0)


class ApprovalTests(PayrollTestCase):
    def setUp(self):
        super().setUp()
        self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 17)
        self.period = self.generate()

    def test_approving_stamps_the_period_and_every_record(self):
        services.approve(self.period, user=self.owner)
        self.period.refresh_from_db()
        record = PayrollRecord.objects.get()
        self.assertEqual(self.period.status, 'APPROVED')
        self.assertEqual(self.period.approved_by, self.owner)
        self.assertIsNotNone(self.period.approved_at)
        self.assertEqual(record.status, 'APPROVED')
        self.assertEqual(record.approved_by, self.owner)

    def test_approving_twice_is_refused(self):
        services.approve(self.period, user=self.owner)
        with self.assertRaises(services.PayrollError):
            services.approve(self.period, user=self.owner)

    def test_a_second_approval_over_the_api_is_a_conflict(self):
        owner = self.client_for(self.owner)
        url = reverse('payroll-period-approve', args=[self.period.id])
        self.assertEqual(owner.post(url, {}, format='json').status_code, 200)
        second = owner.post(url, {}, format='json')
        self.assertEqual(second.status_code, 409)
        self.assertIn('already been approved', second.data['error'])

    def test_an_approved_week_cannot_be_regenerated(self):
        services.approve(self.period, user=self.owner)
        with self.assertRaises(services.PayrollError):
            self.generate()

    def test_regeneration_after_approval_does_not_change_the_figures(self):
        services.approve(self.period, user=self.owner)
        try:
            self.generate()
        except services.PayrollError:
            pass
        record = PayrollRecord.objects.get()
        self.assertEqual(record.gross_earnings, Decimal('800.00'))
        self.assertEqual(record.status, 'APPROVED')

    def test_an_approved_week_cannot_be_edited_over_the_api(self):
        services.approve(self.period, user=self.owner)
        owner = self.client_for(self.owner)
        record = PayrollRecord.objects.get()
        for url in (reverse('payroll-period-detail', args=[self.period.id]),
                    reverse('payroll-record-detail', args=[record.id])):
            self.assertEqual(owner.patch(url, {'status': 'DRAFT'},
                                         format='json').status_code, 405)
            self.assertEqual(owner.delete(url).status_code, 405)

    def test_approval_is_refused_when_there_is_nothing_to_approve(self):
        empty = services.generate(date(2026, 10, 5), user=self.owner)
        with self.assertRaises(services.PayrollError):
            services.approve(empty, user=self.owner)

    def test_approval_is_logged(self):
        self.client_for(self.owner).post(
            reverse('payroll-period-approve', args=[self.period.id]), {},
            format='json')
        self.assertTrue(
            UniversalActivity.objects.filter(action='PAYROLL_APPROVED').exists())


class AttendanceToPayrollTests(PayrollTestCase):
    """The whole chain, over HTTP, the way it will actually be used."""

    def test_check_in_check_out_generate_correct_regenerate_approve(self):
        self.profile(self.anita, '100.00')
        anita = self.client_for(self.anita_user)
        owner = self.client_for(self.owner)

        anita.post(reverse('staff-attendance-check-in'), {}, format='json')
        anita.post(reverse('staff-attendance-check-out'), {}, format='json')
        session = AttendanceSession.objects.get()

        # Give the session a known shape so the arithmetic is checkable.
        owner.post(reverse('staff-attendance-correct', args=[session.id]),
                   {'check_in': '2026-09-01T09:00:00',
                    'check_out': '2026-09-01T17:00:00',
                    'reason': 'Recording the real hours'}, format='json')

        response = owner.post(reverse('payroll-period-generate'),
                              {'week': '2026-09-01'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['records'][0]['worked_minutes'], 480)
        self.assertEqual(response.data['records'][0]['gross_earnings'], '800.00')

        # A further correction, then regenerate: the draft follows attendance.
        owner.post(reverse('staff-attendance-correct', args=[session.id]),
                   {'check_in': '2026-09-01T09:00:00',
                    'check_out': '2026-09-01T18:00:00',
                    'reason': 'Stayed an extra hour'}, format='json')
        response = owner.post(reverse('payroll-period-generate'),
                              {'week': '2026-09-01'}, format='json')
        self.assertEqual(response.data['records'][0]['gross_earnings'], '900.00')

        period = PayrollPeriod.objects.get()
        approved = owner.post(reverse('payroll-period-approve', args=[period.id]),
                              {}, format='json')
        self.assertEqual(approved.status_code, 200, approved.data)
        self.assertEqual(approved.data['status'], 'APPROVED')

        # And now it is frozen against further attendance changes.
        owner.post(reverse('staff-attendance-correct', args=[session.id]),
                   {'check_in': '2026-09-01T06:00:00',
                    'check_out': '2026-09-01T20:00:00',
                    'reason': 'Should not reach payroll'}, format='json')
        self.assertEqual(PayrollRecord.objects.get().gross_earnings,
                         Decimal('900.00'))

    def test_payroll_uses_corrected_times_not_original_ones(self):
        self.profile(self.anita, '100.00')
        session = self.session(self.anita, 1, 9, 18, start_minute=45)  # 09:45-18:00
        self.client_for(self.owner).post(
            reverse('staff-attendance-correct', args=[session.id]),
            {'check_in': '2026-09-01T09:00:00', 'reason': 'Forgot to check in'},
            format='json')
        record = self.generate().records.get()
        self.assertEqual(record.worked_minutes, 540)


class PayrollAccessTests(PayrollTestCase):
    """Every role, against every payroll endpoint. Owner only."""

    def setUp(self):
        super().setUp()
        self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 17)
        self.period = self.generate()
        self.record = self.period.records.get()

        self.master_user = User.objects.create_user(
            username='mira@payroll.test', email='mira@payroll.test',
            password='mirapass12345')
        self.master = Tailor.objects.create(
            name='Mira', specialty='Supervision', role='Master',
            email='mira@payroll.test', user=self.master_user)

    def _urls(self):
        return [
            reverse('payroll-period-list'),
            reverse('payroll-period-detail', args=[self.period.id]),
            reverse('payroll-record-list'),
            reverse('payroll-record-detail', args=[self.record.id]),
        ]

    def test_owner_reads_everything(self):
        owner = self.client_for(self.owner)
        for url in self._urls():
            self.assertEqual(owner.get(url).status_code, 200, url)

    def _refused_or_empty(self, client, who):
        """The Phase 6 matrix (brief section 35).

        Periods are Owner-only and answer 403. Records answer for the caller's
        OWN rows only: a list is 200 and empty for someone with none, and a
        colleague's detail is a scoped 404. In every case no wage figure may
        appear in the body.
        """
        period_list, period_detail, record_list, record_detail = self._urls()
        self.assertEqual(client.get(period_list).status_code, 403, who)
        self.assertEqual(client.get(period_detail).status_code, 403, who)
        listing = client.get(record_list)
        self.assertEqual(listing.status_code, 200, who)
        self.assertEqual(listing.data, [], who)
        self.assertEqual(client.get(record_detail).status_code, 404, who)
        for url in self._urls():
            body = client.get(url).content.decode()
            self.assertNotIn('800.00', body, who)
            self.assertNotIn('100.00', body, who)

    def test_a_master_is_refused_every_payroll_endpoint(self):
        self._refused_or_empty(self.client_for(self.master_user), 'master')

    def test_a_master_cannot_generate_or_approve(self):
        master = self.client_for(self.master_user)
        self.assertEqual(master.post(reverse('payroll-period-generate'),
                                     {'week': '2026-09-01'},
                                     format='json').status_code, 403)
        self.assertEqual(master.post(
            reverse('payroll-period-approve', args=[self.period.id]), {},
            format='json').status_code, 403)
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, 'DRAFT')

    def test_a_tailor_is_refused_every_payroll_endpoint(self):
        """Anita OWNS the fixture record, so her list holds exactly her row."""
        tailor = self.client_for(self.anita_user)
        period_list, period_detail, record_list, record_detail = self._urls()
        self.assertEqual(tailor.get(period_list).status_code, 403)
        self.assertEqual(tailor.get(period_detail).status_code, 403)
        listing = tailor.get(record_list)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual([r['staff_name_snapshot'] for r in listing.data], ['Anita'])
        self.assertEqual(tailor.get(record_detail).status_code, 200)

    def test_a_tailor_cannot_generate_payroll(self):
        response = self.client_for(self.anita_user).post(
            reverse('payroll-period-generate'), {'week': '2026-09-01'},
            format='json')
        self.assertEqual(response.status_code, 403)

    def test_a_tailor_cannot_approve_their_own_payroll(self):
        response = self.client_for(self.anita_user).post(
            reverse('payroll-period-approve', args=[self.period.id]), {},
            format='json')
        self.assertEqual(response.status_code, 403)
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, 'DRAFT')

    def test_a_designer_is_refused(self):
        from apps.design_studio.models import Designer
        user = User.objects.create_user(
            username='dia@payroll.test', email='dia@payroll.test',
            password='diapass12345')
        Designer.objects.create(name='Dia', email='dia@payroll.test', user=user)
        self._refused_or_empty(self.client_for(user), 'designer')

    def test_an_anonymous_caller_is_refused(self):
        anonymous = APIClient()
        anonymous.credentials(HTTP_X_TENANT_ID=self.tenant.schema_name)
        for url in self._urls():
            self.assertIn(anonymous.get(url).status_code, (401, 403), url)

    def test_no_wage_leaks_in_a_refusal_body(self):
        """A Master learns nothing; Anita sees only her own figure."""
        master = self.client_for(self.master_user)
        for url in self._urls():
            body = master.get(url).content.decode()
            self.assertNotIn('800.00', body)
            self.assertNotIn('100.00', body)
        # Anita's own record is hers to read; nothing of anyone else's.
        anita = self.client_for(self.anita_user)
        body = anita.get(self._urls()[2]).content.decode()
        self.assertNotIn('Balan', body)

    def test_payroll_is_not_reachable_through_the_staff_endpoints(self):
        """The roster and employment endpoints must not have grown a wage."""
        owner = self.client_for(self.owner)
        # Field names, not the substring "payroll" -- these fixtures use
        # @payroll.test email addresses, and a naive search matches those.
        for url in (reverse('tailor-list'), reverse('staff-profile-list')):
            body = owner.get(url).content.decode()
            for leaked in ('gross_earnings', 'hourly_rate_snapshot',
                           'worked_minutes', 'payroll_records',
                           'session_breakdown'):
                self.assertNotIn(leaked, body)


class CustomerMoneyUntouchedTests(PayrollTestCase):
    """Payroll must not reach into customer billing. Different direction entirely."""

    def test_generating_and_approving_leaves_orders_alone(self):
        customer = Customer.objects.create(
            first_name='Rhea', last_name='Nair', mobile_number='9600000123')
        order = Order.objects.create(
            order_id='T2B-PAY-0001', customer=customer,
            total_amount=Decimal('95000.00'), advance_paid=Decimal('20000.00'),
            amount_paid=Decimal('20000.00'), payment_status='Partially Paid')
        before = (order.total_amount, order.advance_paid, order.amount_paid,
                  order.payment_status)

        self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 17)
        services.approve(self.generate(), user=self.owner)

        order.refresh_from_db()
        self.assertEqual(
            (order.total_amount, order.advance_paid, order.amount_paid,
             order.payment_status), before)

    def test_payroll_creates_no_order_or_customer_rows(self):
        self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 17)
        services.approve(self.generate(), user=self.owner)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Customer.objects.count(), 0)


class PayrollModuleGateTests(PayrollTestCase):
    def test_payroll_has_its_own_switch(self):
        from core.modules import module_for_path
        self.assertEqual(module_for_path('/api/payroll/periods/'), 'payroll')

    def test_switching_payroll_off_does_not_switch_staff_off(self):
        from core.modules import module_for_path
        self.assertEqual(module_for_path('/api/staff/attendance/'), 'staff')

    def test_payroll_is_on_for_a_boutique_with_no_opinion(self):
        from core.modules import default_enabled, is_enabled
        self.assertTrue(is_enabled({}, 'payroll'))
        self.assertIs(default_enabled()['payroll'], True)


class CrossTenantPayrollTests(TransactionTestCase):
    """Two real boutique schemas. A wage must not cross between them."""

    def setUp(self):
        connection.set_schema_to_public()
        self.alpha = self._boutique('pay_alpha', 'owner@payalpha.test', 'Alpha')
        self.beta = self._boutique('pay_beta', 'owner@paybeta.test', 'Beta')
        self._payroll(self.alpha, 'alpha@payalpha.test', 'Alpha Tailor', '111.00')
        self._payroll(self.beta, 'beta@paybeta.test', 'Beta Tailor', '222.00')
        connection.set_schema_to_public()

    def tearDown(self):
        connection.set_schema_to_public()
        for schema in ('pay_alpha', 'pay_beta'):
            with connection.cursor() as c:
                c.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            BoutiqueTenant.objects.filter(schema_name=schema).delete()

    @staticmethod
    def _boutique(schema, owner_email, name):
        tenant = BoutiqueTenant(schema_name=schema, owner_email=owner_email,
                                name=name, timezone='Asia/Kolkata')
        tenant.save()
        return tenant

    @staticmethod
    def _payroll(tenant, email, name, rate):
        with schema_context(tenant.schema_name):
            owner = User.objects.create_user(
                username=tenant.owner_email, email=tenant.owner_email,
                password='ownerpw12345')
            Token.objects.get_or_create(user=owner)
            user = User.objects.create_user(
                username=email, email=email, password='staffpw12345')
            tailor = Tailor.objects.create(
                name=name, specialty='Stitching', role='Tailor',
                email=email, user=user)
            StaffProfile.objects.create(staff=tailor, hourly_rate=Decimal(rate))
            s = AttendanceSession(
                staff=tailor, date=date(2026, 9, 1),
                check_in=datetime(2026, 9, 1, 9, tzinfo=tenant_timezone(tenant)),
                check_out=datetime(2026, 9, 1, 17, tzinfo=tenant_timezone(tenant)))
            s.minutes = s.duration_minutes()
            s.save()
            services.generate(date(2026, 9, 1), user=owner)

    def _client(self, tenant):
        with schema_context(tenant.schema_name):
            token = Token.objects.get(user__email=tenant.owner_email).key
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Token {token}',
                        HTTP_X_TENANT_ID=tenant.schema_name)
        return api

    def test_each_boutique_sees_only_its_own_payroll(self):
        response = self._client(self.alpha).get(reverse('payroll-record-list'))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('111.00', body)
        self.assertNotIn('222.00', body)
        self.assertNotIn('Beta Tailor', body)

    def test_a_token_from_one_boutique_is_not_valid_in_another(self):
        with schema_context(self.alpha.schema_name):
            stolen = Token.objects.get(user__email='owner@payalpha.test').key
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Token {stolen}',
                        HTTP_X_TENANT_ID=self.beta.schema_name)
        response = api.get(reverse('payroll-record-list'))
        self.assertIn(response.status_code, (401, 403))
        self.assertNotIn('222.00', response.content.decode())

    def test_a_payroll_id_from_another_boutique_is_not_found(self):
        with schema_context(self.beta.schema_name):
            beta_record = PayrollRecord.objects.get()
        response = self._client(self.alpha).get(
            reverse('payroll-record-detail', args=[beta_record.id]))
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('222.00', response.content.decode())

    def test_approving_in_one_boutique_leaves_the_other_alone(self):
        with schema_context(self.alpha.schema_name):
            period = PayrollPeriod.objects.get()
        self._client(self.alpha).post(
            reverse('payroll-period-approve', args=[period.id]), {}, format='json')
        with schema_context(self.beta.schema_name):
            self.assertEqual(PayrollPeriod.objects.get().status, 'DRAFT')


class RoundingTieTests(PayrollTestCase):
    """Exact half-paise boundaries -- the cases the first version got wrong.

    The original implementation divided minutes by 60 BEFORE applying the rate.
    Decimal division rounds to the context precision, so the quotient was
    already approximate and landed a hair under the tie; ROUND_HALF_UP then
    rounded down where exact arithmetic rounds up. Always downwards, so always
    against the person being paid. None of the round-number examples in
    GrossCalculationTests crosses a tie, which is why they all passed.
    """

    def test_the_reported_tie(self):
        """242 minutes at Rs.18.75 is exactly 75.625, which owes 75.63."""
        self.assertEqual(services.gross_for(242, Decimal('18.75')),
                         Decimal('75.63'))

    def test_a_tie_at_a_realistic_rate(self):
        """242 minutes at Rs.150.15 is exactly 605.605, which owes 605.61."""
        self.assertEqual(services.gross_for(242, Decimal('150.15')),
                         Decimal('605.61'))

    def test_ties_round_up_across_a_sweep(self):
        """Every exact half-paise tie must round up, not down.

        Compared against Fraction arithmetic, which has no rounding at all, so
        the assertion is against the true value rather than against another
        Decimal expression that could share the same flaw.
        """
        from fractions import Fraction
        import math
        for minutes in range(1, 400):
            for cents in range(1000, 30001, 625):
                rate = Decimal(cents) / 100
                scaled = Fraction(minutes) * Fraction(cents, 100) / 60 * 100
                floor = math.floor(scaled)
                exact = Decimal(
                    floor + 1 if scaled - floor >= Fraction(1, 2) else floor
                ) / Decimal(100)
                self.assertEqual(
                    services.gross_for(minutes, rate), exact,
                    f'{minutes} min at {rate}')

    def test_a_tie_reaches_the_stored_record(self):
        """Not just the helper -- the number that gets frozen must be right."""
        self.profile(self.anita, '18.75')
        self.session(self.anita, 1, 9, 13, end_minute=2)   # 09:00-13:02 = 242 min
        record = self.generate().records.get()
        self.assertEqual(record.worked_minutes, 242)
        self.assertEqual(record.gross_earnings, Decimal('75.63'))


class ActivityFeedConfidentialityTests(PayrollTestCase):
    """UniversalActivity is readable by Masters. No wage may travel in it."""

    def setUp(self):
        super().setUp()
        self.master_user = User.objects.create_user(
            username='mira@payroll.test', email='mira@payroll.test',
            password='mirapass12345')
        Tailor.objects.create(
            name='Mira', specialty='Supervision', role='Master',
            email='mira@payroll.test', user=self.master_user)

    def test_no_money_is_written_to_the_activity_feed(self):
        self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 17)
        owner = self.client_for(self.owner)
        owner.post(reverse('payroll-period-generate'), {'week': '2026-09-01'},
                   format='json')
        period = PayrollPeriod.objects.get()
        owner.post(reverse('payroll-period-approve', args=[period.id]), {},
                   format='json')

        for entry in UniversalActivity.objects.all():
            blob = (f"{entry.title} {entry.description} "
                    f"{entry.old_value} {entry.new_value}")
            for figure in ('800.00', '800', '100.00', 'gross'):
                self.assertNotIn(figure, blob)

    def test_a_master_reading_the_feed_learns_no_wage(self):
        self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 17)
        owner = self.client_for(self.owner)
        owner.post(reverse('payroll-period-generate'), {'week': '2026-09-01'},
                   format='json')
        period = PayrollPeriod.objects.get()
        owner.post(reverse('payroll-period-approve', args=[period.id]), {},
                   format='json')

        response = self.client_for(self.master_user).get(
            '/api/activities/activities/')
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertNotIn('800.00', body)
        self.assertNotIn('4250', body)


class NoDoublePaymentTests(PayrollTestCase):
    """One attendance session is paid at most once, ever."""

    def test_a_session_moved_into_the_next_week_is_not_paid_again(self):
        """The path: correct an approved week's session across the boundary.

        A session's `date` follows its check-in, so an owner correcting a
        Sunday-night start into Monday moves it into the following week. The
        approved week has already paid it and cannot be changed, so without a
        guard the next run pays for the same hours a second time.
        """
        self.profile(self.anita, '100.00')
        # Sunday 6 September, the last day of the first week.
        session = self.session(self.anita, 6, 9, 17)
        first = self.generate()
        self.assertEqual(first.records.get().gross_earnings, Decimal('800.00'))
        services.approve(first, user=self.owner)

        # Now it is corrected into the following Monday.
        session.check_in = self.at(7, 9, month=9)
        session.check_out = self.at(7, 17, month=9)
        session.date = date(2026, 9, 7)
        session.save()

        second = services.generate(date(2026, 9, 7), user=self.owner)
        self.assertEqual(second.records.count(), 0,
                         'the same session must not be paid a second time')

    def test_a_session_paid_in_an_approved_week_is_excluded_from_later_drafts(self):
        self.profile(self.anita, '100.00')
        session = self.session(self.anita, 1, 9, 17)
        services.approve(self.generate(), user=self.owner)
        self.assertIn(str(session.id),
                      services.already_paid_session_ids(self.anita))

    def test_a_draft_week_does_not_lock_its_sessions(self):
        """Only APPROVED runs consume a session. A draft must stay re-runnable."""
        self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 17)
        self.generate()
        self.assertEqual(services.already_paid_session_ids(self.anita), set())
        self.assertEqual(self.generate().records.get().gross_earnings,
                         Decimal('800.00'))


class DepositAgreementTests(PayrollTestCase):
    """The agreement is ledger history, not a column somebody edits."""

    def test_setting_a_deposit_writes_an_agreement_entry(self):
        response = self.client_for(self.owner).post(
            reverse('staff-profile-list'),
            {'staff': self.anita.id, 'hourly_rate': '100.00',
             'deposit_total': '5000.00', 'deposit_weekly': '500.00'},
            format='json')
        self.assertEqual(response.status_code, 201, response.data)
        entry = StaffLedgerEntry.objects.get()
        self.assertEqual(entry.entry_type, 'DEPOSIT_AGREED')
        self.assertEqual(entry.amount, Decimal('5000.00'))
        self.assertEqual(deposits.deposit_state(self.anita)['agreed'],
                         Decimal('5000.00'))

    def test_no_deposit_means_no_ledger_history(self):
        self.client_for(self.owner).post(
            reverse('staff-profile-list'),
            {'staff': self.anita.id, 'hourly_rate': '100.00'}, format='json')
        self.assertEqual(StaffLedgerEntry.objects.count(), 0)
        self.assertEqual(deposits.deposit_state(self.anita)['agreed'], Decimal('0.00'))

    def test_saving_an_unchanged_profile_does_not_append_a_duplicate(self):
        owner = self.client_for(self.owner)
        created = owner.post(
            reverse('staff-profile-list'),
            {'staff': self.anita.id, 'deposit_total': '5000.00'}, format='json')
        owner.patch(reverse('staff-profile-detail', args=[created.data['id']]),
                    {'phone': '9600000000'}, format='json')
        self.assertEqual(StaffLedgerEntry.objects.count(), 1)

    def test_changing_the_terms_appends_rather_than_rewrites(self):
        owner = self.client_for(self.owner)
        created = owner.post(
            reverse('staff-profile-list'),
            {'staff': self.anita.id, 'deposit_total': '5000.00'}, format='json')
        owner.patch(reverse('staff-profile-detail', args=[created.data['id']]),
                    {'deposit_total': '3000.00'}, format='json')
        entries = list(StaffLedgerEntry.objects.order_by('created_at'))
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].amount, Decimal('5000.00'))
        self.assertEqual(entries[1].amount, Decimal('3000.00'))
        # The newest agreement is the live one.
        self.assertEqual(deposits.deposit_state(self.anita)['agreed'],
                         Decimal('3000.00'))

    def test_reducing_the_agreement_does_not_undo_past_recoveries(self):
        """5,000 agreed, 2,000 recovered, reduced to 3,000 -> 1,000 still owed."""
        profile = self.profile(self.anita, '100.00', deposit_total=Decimal('5000.00'),
                               deposit_weekly=Decimal('500.00'))
        deposits.record_agreement(self.anita, Decimal('5000.00'), user=self.owner)
        for _ in range(4):
            StaffLedgerEntry.objects.create(
                staff=self.anita, staff_name_snapshot='Anita',
                entry_type='DEPOSIT_RECOVERY', amount=Decimal('500.00'),
                payroll_record=self._throwaway_record())
        self.assertEqual(deposits.deposit_state(self.anita)['recovered'],
                         Decimal('2000.00'))

        deposits.record_agreement(self.anita, Decimal('3000.00'), user=self.owner)
        state = deposits.deposit_state(self.anita)
        self.assertEqual(state['agreed'], Decimal('3000.00'))
        self.assertEqual(state['recovered'], Decimal('2000.00'))
        self.assertEqual(state['remaining'], Decimal('1000.00'))

    def _throwaway_record(self):
        """A distinct PayrollRecord, so each recovery satisfies the unique index."""
        period = PayrollPeriod.objects.create(
            period_start=date(2020, 1, 6) + timedelta(days=7 * self._seq()),
            period_end=date(2020, 1, 12) + timedelta(days=7 * self._seq()))
        return PayrollRecord.objects.create(
            period=period, staff=self.anita, staff_name_snapshot='Anita',
            worked_minutes=0, regular_minutes=0)

    _counter = 0

    def _seq(self):
        type(self)._counter += 1
        return type(self)._counter

    def test_a_negative_deposit_is_refused_by_the_database(self):
        with self.assertRaises(IntegrityError):
            StaffLedgerEntry.objects.create(
                staff=self.anita, staff_name_snapshot='Anita',
                entry_type='DEPOSIT_AGREED', amount=Decimal('-1.00'))

    def test_a_recovery_must_name_its_payroll(self):
        with self.assertRaises(IntegrityError):
            StaffLedgerEntry.objects.create(
                staff=self.anita, staff_name_snapshot='Anita',
                entry_type='DEPOSIT_RECOVERY', amount=Decimal('100.00'))


class DepositRecoveryCalculationTests(PayrollTestCase):
    """The clamps, in isolation from payroll."""

    def setUp(self):
        super().setUp()
        self.p = self.profile(self.anita, '100.00',
                              deposit_total=Decimal('5000.00'),
                              deposit_weekly=Decimal('500.00'))
        deposits.record_agreement(self.anita, Decimal('5000.00'), user=self.owner)

    def test_the_ordinary_week(self):
        r = deposits.recovery_for(self.anita, self.p, Decimal('4250.00'))
        self.assertEqual(r['scheduled'], Decimal('500.00'))
        self.assertEqual(r['recovered'], Decimal('500.00'))
        self.assertEqual(r['unrecovered'], Decimal('0.00'))
        self.assertEqual(r['balance_after'], Decimal('4500.00'))

    def test_a_thin_week_recovers_only_what_was_earned(self):
        r = deposits.recovery_for(self.anita, self.p, Decimal('300.00'))
        self.assertEqual(r['scheduled'], Decimal('500.00'))
        self.assertEqual(r['recovered'], Decimal('300.00'))
        self.assertEqual(r['unrecovered'], Decimal('200.00'))
        self.assertEqual(r['balance_after'], Decimal('4700.00'))

    def test_a_week_with_no_earnings_recovers_nothing(self):
        r = deposits.recovery_for(self.anita, self.p, Decimal('0.00'))
        self.assertEqual(r['recovered'], Decimal('0.00'))
        self.assertEqual(r['unrecovered'], Decimal('500.00'))
        self.assertEqual(r['balance_after'], Decimal('5000.00'))

    def test_an_unpayable_record_recovers_nothing(self):
        r = deposits.recovery_for(self.anita, self.p, None)
        self.assertEqual(r['recovered'], Decimal('0.00'))

    def test_the_final_week_takes_only_what_is_left(self):
        StaffLedgerEntry.objects.create(
            staff=self.anita, staff_name_snapshot='Anita',
            entry_type='DEPOSIT_RECOVERY', amount=Decimal('4750.00'),
            payroll_record=self._record())
        r = deposits.recovery_for(self.anita, self.p, Decimal('2000.00'))
        self.assertEqual(r['scheduled'], Decimal('250.00'))
        self.assertEqual(r['recovered'], Decimal('250.00'))
        self.assertEqual(r['balance_after'], Decimal('0.00'))

    def test_a_fully_recovered_deposit_takes_nothing_more(self):
        StaffLedgerEntry.objects.create(
            staff=self.anita, staff_name_snapshot='Anita',
            entry_type='DEPOSIT_RECOVERY', amount=Decimal('5000.00'),
            payroll_record=self._record())
        r = deposits.recovery_for(self.anita, self.p, Decimal('2000.00'))
        self.assertEqual(r['scheduled'], Decimal('0.00'))
        self.assertEqual(r['recovered'], Decimal('0.00'))
        self.assertEqual(r['unrecovered'], Decimal('0.00'))
        self.assertTrue(deposits.deposit_state(self.anita)['fully_recovered'])

    def test_a_staff_member_with_no_deposit_recovers_nothing(self):
        other = self.profile(self.balan, '100.00')
        r = deposits.recovery_for(self.balan, other, Decimal('4000.00'))
        self.assertEqual(r['scheduled'], Decimal('0.00'))
        self.assertEqual(r['recovered'], Decimal('0.00'))

    def test_a_zero_weekly_rule_recovers_nothing(self):
        self.p.deposit_weekly = Decimal('0.00')
        self.p.save()
        r = deposits.recovery_for(self.anita, self.p, Decimal('4000.00'))
        self.assertEqual(r['recovered'], Decimal('0.00'))

    def test_remaining_never_goes_below_zero(self):
        StaffLedgerEntry.objects.create(
            staff=self.anita, staff_name_snapshot='Anita',
            entry_type='DEPOSIT_RECOVERY', amount=Decimal('5000.00'),
            payroll_record=self._record())
        deposits.record_agreement(self.anita, Decimal('3000.00'), user=self.owner)
        state = deposits.deposit_state(self.anita)
        self.assertEqual(state['remaining'], Decimal('0.00'))
        self.assertEqual(state['over_recovered'], Decimal('2000.00'))

    _n = 0

    def _record(self):
        type(self)._n += 1
        period = PayrollPeriod.objects.create(
            period_start=date(2021, 1, 4) + timedelta(days=7 * type(self)._n),
            period_end=date(2021, 1, 10) + timedelta(days=7 * type(self)._n))
        return PayrollRecord.objects.create(
            period=period, staff=self.anita, staff_name_snapshot='Anita',
            worked_minutes=0, regular_minutes=0)


class DepositPayrollIntegrationTests(PayrollTestCase):
    """The mandatory worked examples, end to end through payroll."""

    def _setup(self, rate='100.00', total='5000.00', weekly='500.00'):
        profile = self.profile(self.anita, rate,
                               deposit_total=Decimal(total),
                               deposit_weekly=Decimal(weekly))
        deposits.record_agreement(self.anita, Decimal(total), user=self.owner)
        return profile

    def test_the_headline_example(self):
        """5,000 deposit, 500 weekly, 4,250 gross -> 500 taken, 3,750 net, 4,500 left."""
        self._setup()
        self.session(self.anita, 1, 9, 17)     # 480
        self.session(self.anita, 2, 9, 17)     # 480
        self.session(self.anita, 3, 9, 17)     # 480
        self.session(self.anita, 4, 9, 17)     # 480
        self.session(self.anita, 5, 9, 17, end_minute=30)   # 510  => 2430
        self.session(self.anita, 6, 9, 11)     # 120  => 2550 = 42h30m
        period = self.generate()
        record = period.records.get()
        self.assertEqual(record.gross_earnings, Decimal('4250.00'))
        self.assertEqual(record.deposit_scheduled, Decimal('500.00'))
        self.assertEqual(record.deposit_recovered, Decimal('500.00'))
        self.assertEqual(record.net_before_other_deductions, Decimal('3750.00'))
        self.assertEqual(record.deposit_balance_after, Decimal('4500.00'))

        services.approve(period, user=self.owner)
        self.assertEqual(deposits.deposit_state(self.anita)['remaining'],
                         Decimal('4500.00'))

    def test_the_low_earning_example(self):
        """5,000 remaining, 500 weekly, 300 gross -> 300 taken, 0 net, 200 missed."""
        self._setup()
        self.session(self.anita, 1, 9, 12)     # 180 min at 100 = 300.00
        record = self.generate().records.get()
        self.assertEqual(record.gross_earnings, Decimal('300.00'))
        self.assertEqual(record.deposit_scheduled, Decimal('500.00'))
        self.assertEqual(record.deposit_recovered, Decimal('300.00'))
        self.assertEqual(record.deposit_unrecovered, Decimal('200.00'))
        self.assertEqual(record.net_before_other_deductions, Decimal('0.00'))
        self.assertEqual(record.deposit_balance_after, Decimal('4700.00'))

    def test_the_final_recovery_example(self):
        """250 left, 500 weekly, 2,000 gross -> 250 taken, then nothing ever again."""
        self._setup()
        # Recover 4,750 through an earlier approved week.
        self.session(self.anita, 1, 9, 17)
        first = self.generate()
        first.records.update(deposit_recovered=Decimal('4750.00'))
        services.approve(first, user=self.owner)
        self.assertEqual(deposits.deposit_state(self.anita)['remaining'],
                         Decimal('250.00'))

        self.session(self.anita, 8, 9, 17, month=9)
        second = services.generate(date(2026, 9, 8), user=self.owner)
        record = second.records.get()
        self.assertEqual(record.deposit_scheduled, Decimal('250.00'))
        self.assertEqual(record.deposit_recovered, Decimal('250.00'))
        services.approve(second, user=self.owner)
        self.assertEqual(deposits.deposit_state(self.anita)['remaining'],
                         Decimal('0.00'))

        # And the week after takes nothing.
        self.session(self.anita, 15, 9, 17, month=9)
        third = services.generate(date(2026, 9, 15), user=self.owner)
        self.assertEqual(third.records.get().deposit_recovered, Decimal('0.00'))
        self.assertEqual(third.records.get().deposit_scheduled, Decimal('0.00'))

    def test_a_staff_member_without_a_deposit_is_unaffected(self):
        self.profile(self.anita, '100.00')
        self.session(self.anita, 1, 9, 17)
        record = self.generate().records.get()
        self.assertEqual(record.gross_earnings, Decimal('800.00'))
        self.assertEqual(record.deposit_recovered, Decimal('0.00'))
        self.assertEqual(record.net_before_other_deductions, Decimal('800.00'))

    def test_net_pay_never_goes_negative(self):
        self._setup(weekly='99999.00')
        self.session(self.anita, 1, 9, 10)   # 60 min = 100.00 gross
        record = self.generate().records.get()
        self.assertEqual(record.net_before_other_deductions, Decimal('0.00'))
        self.assertGreaterEqual(record.net_before_other_deductions, Decimal('0.00'))

    def test_the_gross_calculation_is_untouched_by_the_deposit_layer(self):
        """Phase 4's figures must be identical whether or not a deposit exists."""
        self.profile(self.balan, '100.00')
        self._setup()
        self.session(self.anita, 1, 9, 17)
        self.session(self.balan, 1, 9, 17)
        by_name = {r.staff_name_snapshot: r
                   for r in self.generate().records.all()}
        self.assertEqual(by_name['Anita'].gross_earnings, Decimal('800.00'))
        self.assertEqual(by_name['Balan'].gross_earnings, Decimal('800.00'))
        self.assertEqual(by_name['Anita'].worked_minutes,
                         by_name['Balan'].worked_minutes)


class DepositIdempotencyTests(PayrollTestCase):
    """A rupee is recovered exactly once."""

    def setUp(self):
        super().setUp()
        self.profile(self.anita, '100.00', deposit_total=Decimal('5000.00'),
                     deposit_weekly=Decimal('500.00'))
        deposits.record_agreement(self.anita, Decimal('5000.00'), user=self.owner)
        self.session(self.anita, 1, 9, 17)

    def test_drafting_repeatedly_moves_no_money(self):
        for _ in range(4):
            self.generate()
        self.assertEqual(
            StaffLedgerEntry.objects.filter(entry_type='DEPOSIT_RECOVERY').count(),
            0)
        self.assertEqual(deposits.deposit_state(self.anita)['recovered'],
                         Decimal('0.00'))

    def test_approval_writes_exactly_one_recovery(self):
        services.approve(self.generate(), user=self.owner)
        self.assertEqual(
            StaffLedgerEntry.objects.filter(entry_type='DEPOSIT_RECOVERY').count(),
            1)

    def test_a_second_approval_creates_no_second_recovery(self):
        period = self.generate()
        services.approve(period, user=self.owner)
        with self.assertRaises(services.PayrollError):
            services.approve(period, user=self.owner)
        self.assertEqual(
            StaffLedgerEntry.objects.filter(entry_type='DEPOSIT_RECOVERY').count(),
            1)
        self.assertEqual(deposits.deposit_state(self.anita)['recovered'],
                         Decimal('500.00'))

    def test_a_second_approval_over_the_api_creates_no_second_recovery(self):
        period = self.generate()
        owner = self.client_for(self.owner)
        url = reverse('payroll-period-approve', args=[period.id])
        self.assertEqual(owner.post(url, {}, format='json').status_code, 200)
        self.assertEqual(owner.post(url, {}, format='json').status_code, 409)
        self.assertEqual(
            StaffLedgerEntry.objects.filter(entry_type='DEPOSIT_RECOVERY').count(),
            1)

    def test_the_database_refuses_two_recoveries_for_one_payroll(self):
        period = self.generate()
        services.approve(period, user=self.owner)
        record = period.records.get()
        with self.assertRaises(IntegrityError):
            StaffLedgerEntry.objects.create(
                staff=self.anita, staff_name_snapshot='Anita',
                entry_type='DEPOSIT_RECOVERY', amount=Decimal('500.00'),
                payroll_record=record)

    def test_approval_is_refused_if_the_obligation_shrank_under_the_draft(self):
        """A stale draft must not collect more than is still owed."""
        period = self.generate()
        # Someone else's approval took the deposit down in the meantime.
        StaffLedgerEntry.objects.create(
            staff=self.anita, staff_name_snapshot='Anita',
            entry_type='DEPOSIT_RECOVERY', amount=Decimal('4900.00'),
            payroll_record=PayrollRecord.objects.create(
                period=PayrollPeriod.objects.create(
                    period_start=date(2019, 1, 7), period_end=date(2019, 1, 13)),
                staff=self.anita, staff_name_snapshot='Anita',
                worked_minutes=0, regular_minutes=0))
        with self.assertRaises(services.PayrollError) as caught:
            services.approve(period, user=self.owner)
        self.assertIn('changed since', str(caught.exception))
        period.refresh_from_db()
        self.assertEqual(period.status, 'DRAFT')

    def test_recovery_never_exceeds_the_obligation(self):
        period = self.generate()
        period.records.update(deposit_recovered=Decimal('99999.00'))
        with self.assertRaises(services.PayrollError):
            services.approve(period, user=self.owner)
        self.assertEqual(
            StaffLedgerEntry.objects.filter(entry_type='DEPOSIT_RECOVERY').count(),
            0)


class DepositImmutabilityTests(PayrollTestCase):
    """Approved payroll and its recovery are history, not live values."""

    def setUp(self):
        super().setUp()
        self.p = self.profile(self.anita, '100.00',
                              deposit_total=Decimal('5000.00'),
                              deposit_weekly=Decimal('500.00'))
        deposits.record_agreement(self.anita, Decimal('5000.00'), user=self.owner)
        self.session(self.anita, 1, 9, 17)
        self.period = self.generate()
        services.approve(self.period, user=self.owner)
        self.record = self.period.records.get()

    def test_changing_the_terms_does_not_move_an_approved_week(self):
        self.p.deposit_weekly = Decimal('50.00')
        self.p.deposit_total = Decimal('1000.00')
        self.p.save()
        self.record.refresh_from_db()
        self.assertEqual(self.record.deposit_recovered, Decimal('500.00'))
        self.assertEqual(self.record.gross_earnings, Decimal('800.00'))
        self.assertEqual(self.record.net_before_other_deductions, Decimal('300.00'))

    def test_correcting_attendance_afterwards_does_not_move_it_either(self):
        session = AttendanceSession.objects.get()
        self.client_for(self.owner).post(
            reverse('staff-attendance-correct', args=[session.id]),
            {'check_in': '2026-09-01T06:00:00', 'check_out': '2026-09-01T22:00:00',
             'reason': 'Should not reach approved payroll'}, format='json')
        self.record.refresh_from_db()
        self.assertEqual(self.record.gross_earnings, Decimal('800.00'))
        self.assertEqual(self.record.deposit_recovered, Decimal('500.00'))

    def test_the_recovery_names_the_payroll_that_caused_it(self):
        entry = StaffLedgerEntry.objects.get(entry_type='DEPOSIT_RECOVERY')
        self.assertEqual(entry.payroll_record_id, self.record.id)
        self.assertEqual(entry.balance_before, Decimal('5000.00'))
        self.assertEqual(entry.balance_after, Decimal('4500.00'))

    def test_a_recovered_payroll_cannot_be_deleted_out_from_under_its_ledger(self):
        with self.assertRaises(Exception):
            self.record.delete()


class DepositAccessTests(PayrollTestCase):
    """Deposits are payroll, and payroll is Owner-only."""

    def setUp(self):
        super().setUp()
        self.profile(self.anita, '100.00', deposit_total=Decimal('5000.00'),
                     deposit_weekly=Decimal('500.00'))
        deposits.record_agreement(self.anita, Decimal('5000.00'), user=self.owner)
        self.master_user = User.objects.create_user(
            username='mira@payroll.test', email='mira@payroll.test',
            password='mirapass12345')
        self.master = Tailor.objects.create(
            name='Mira', specialty='Supervision', role='Master',
            email='mira@payroll.test', user=self.master_user)

    def _urls(self):
        return [reverse('payroll-deposit-list'),
                reverse('payroll-deposit-detail', args=[self.anita.id])]

    def test_owner_sees_the_deposit_position(self):
        response = self.client_for(self.owner).get(
            reverse('payroll-deposit-detail', args=[self.anita.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['agreed'], '5000.00')
        self.assertEqual(response.data['remaining'], '5000.00')

    def test_a_master_is_refused(self):
        for url in self._urls():
            self.assertEqual(
                self.client_for(self.master_user).get(url).status_code, 403, url)

    def test_a_tailor_is_refused_even_their_own(self):
        """Self-service payslips are a later phase; nothing is exposed yet."""
        for url in self._urls():
            self.assertEqual(
                self.client_for(self.anita_user).get(url).status_code, 403, url)

    def test_an_anonymous_caller_is_refused(self):
        anonymous = APIClient()
        anonymous.credentials(HTTP_X_TENANT_ID=self.tenant.schema_name)
        for url in self._urls():
            self.assertIn(anonymous.get(url).status_code, (401, 403), url)

    def test_no_deposit_figure_leaks_in_a_refusal(self):
        for url in self._urls():
            body = self.client_for(self.master_user).get(url).content.decode()
            self.assertNotIn('5000', body)

    def test_a_master_reading_the_roster_sees_no_deposit_terms(self):
        """The Phase 2 field-level rule still holds with a ledger behind it."""
        body = self.client_for(self.master_user).get(
            reverse('staff-profile-list')).content.decode()
        self.assertNotIn('deposit_total', body)
        self.assertNotIn('deposit_weekly', body)
        self.assertNotIn('5000', body)

    def test_the_activity_feed_carries_no_deposit_figures(self):
        """Direct regression against the Phase 4 leak: Masters read this feed."""
        owner = self.client_for(self.owner)
        self.session(self.anita, 1, 9, 17)
        owner.post(reverse('payroll-period-generate'), {'week': '2026-09-01'},
                   format='json')
        period = PayrollPeriod.objects.get()
        owner.post(reverse('payroll-period-approve', args=[period.id]), {},
                   format='json')

        for entry in UniversalActivity.objects.all():
            blob = (f"{entry.title} {entry.description} "
                    f"{entry.old_value} {entry.new_value}")
            for figure in ('5000', '4500', '500.00', '800.00'):
                self.assertNotIn(figure, blob)

        feed = self.client_for(self.master_user).get('/api/activities/activities/')
        self.assertEqual(feed.status_code, 200)
        body = feed.content.decode()
        for figure in ('5000', '4500', '800.00'):
            self.assertNotIn(figure, body)


class CrossTenantDepositTests(TransactionTestCase):
    """A deposit belongs to one boutique and cannot be read from another."""

    def setUp(self):
        connection.set_schema_to_public()
        self.alpha = self._boutique('dep_alpha', 'owner@depalpha.test', 'Alpha')
        self.beta = self._boutique('dep_beta', 'owner@depbeta.test', 'Beta')
        self._deposit(self.alpha, 'alpha@depalpha.test', 'Alpha Tailor', '1111.00')
        self._deposit(self.beta, 'beta@depbeta.test', 'Beta Tailor', '2222.00')
        connection.set_schema_to_public()

    def tearDown(self):
        connection.set_schema_to_public()
        for schema in ('dep_alpha', 'dep_beta'):
            with connection.cursor() as c:
                c.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            BoutiqueTenant.objects.filter(schema_name=schema).delete()

    @staticmethod
    def _boutique(schema, owner_email, name):
        tenant = BoutiqueTenant(schema_name=schema, owner_email=owner_email,
                                name=name, timezone='Asia/Kolkata')
        tenant.save()
        return tenant

    @staticmethod
    def _deposit(tenant, email, name, amount):
        with schema_context(tenant.schema_name):
            owner = User.objects.create_user(
                username=tenant.owner_email, email=tenant.owner_email,
                password='ownerpw12345')
            Token.objects.get_or_create(user=owner)
            user = User.objects.create_user(
                username=email, email=email, password='staffpw12345')
            tailor = Tailor.objects.create(
                name=name, specialty='Stitching', role='Tailor',
                email=email, user=user)
            StaffProfile.objects.create(
                staff=tailor, hourly_rate=Decimal('100.00'),
                deposit_total=Decimal(amount), deposit_weekly=Decimal('100.00'))
            deposits.record_agreement(tailor, Decimal(amount), user=owner)

    def _client(self, tenant):
        with schema_context(tenant.schema_name):
            token = Token.objects.get(user__email=tenant.owner_email).key
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Token {token}',
                        HTTP_X_TENANT_ID=tenant.schema_name)
        return api

    def test_each_boutique_sees_only_its_own_deposits(self):
        response = self._client(self.alpha).get(reverse('payroll-deposit-list'))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('1111.00', body)
        self.assertNotIn('2222.00', body)
        self.assertNotIn('Beta Tailor', body)

    def test_a_staff_id_from_another_boutique_is_not_found(self):
        with schema_context(self.beta.schema_name):
            beta_staff = Tailor.objects.get(name='Beta Tailor')
        response = self._client(self.alpha).get(
            reverse('payroll-deposit-detail', args=[beta_staff.id]))
        body = response.content.decode()
        self.assertNotIn('2222.00', body)

    def test_ledger_entries_do_not_cross_schemas(self):
        with schema_context(self.alpha.schema_name):
            self.assertEqual(StaffLedgerEntry.objects.count(), 1)
            self.assertEqual(StaffLedgerEntry.objects.get().amount,
                             Decimal('1111.00'))
        with schema_context(self.beta.schema_name):
            self.assertEqual(StaffLedgerEntry.objects.count(), 1)
            self.assertEqual(StaffLedgerEntry.objects.get().amount,
                             Decimal('2222.00'))


class DepositReviewFixTests(PayrollTestCase):
    """Regressions for defects the adversarial review found after the tests passed."""

    def test_cancelling_a_deposit_stops_recovery(self):
        """Setting the agreed deposit to zero must reach the ledger.

        The first version skipped a zero, so the ledger kept the old agreement
        and payroll went on collecting against a deposit the owner had just
        cancelled -- with nothing in the interface able to stop it.
        """
        owner = self.client_for(self.owner)
        created = owner.post(
            reverse('staff-profile-list'),
            {'staff': self.anita.id, 'hourly_rate': '100.00',
             'deposit_total': '5000.00', 'deposit_weekly': '500.00'},
            format='json')
        self.assertEqual(deposits.deposit_state(self.anita)['remaining'],
                         Decimal('5000.00'))

        owner.patch(reverse('staff-profile-detail', args=[created.data['id']]),
                    {'deposit_total': '0.00'}, format='json')

        state = deposits.deposit_state(self.anita)
        self.assertEqual(state['agreed'], Decimal('0.00'))
        self.assertEqual(state['remaining'], Decimal('0.00'))

        self.session(self.anita, 1, 9, 17)
        record = self.generate().records.get()
        self.assertEqual(record.deposit_recovered, Decimal('0.00'))
        self.assertEqual(record.net_before_other_deductions, Decimal('800.00'))

    def test_a_deleted_staff_member_has_no_pooled_balance(self):
        """staff=None must not match every orphaned ledger row at once."""
        self.profile(self.anita, '100.00', deposit_total=Decimal('5000.00'),
                     deposit_weekly=Decimal('500.00'))
        self.profile(self.balan, '100.00', deposit_total=Decimal('3000.00'),
                     deposit_weekly=Decimal('300.00'))
        deposits.record_agreement(self.anita, Decimal('5000.00'), user=self.owner)
        deposits.record_agreement(self.balan, Decimal('3000.00'), user=self.owner)

        self.anita.delete()
        self.balan.delete()

        # Both agreements are now orphaned. Asking about "no staff member" must
        # answer nothing rather than summing them into one balance.
        self.assertEqual(deposits.deposit_state(None)['agreed'], Decimal('0.00'))
        self.assertEqual(deposits.deposit_state(None)['remaining'], Decimal('0.00'))
        self.assertEqual(StaffLedgerEntry.objects.filter(staff__isnull=True).count(), 2)

    def test_recovery_is_refused_rather_than_silently_reduced(self):
        """A ledger that disagrees with its payroll record is worse than a failure."""
        profile = self.profile(self.anita, '100.00',
                               deposit_total=Decimal('5000.00'),
                               deposit_weekly=Decimal('500.00'))
        deposits.record_agreement(self.anita, Decimal('100.00'), user=self.owner)
        self.session(self.anita, 1, 9, 17)
        period = self.generate()
        period.records.update(deposit_recovered=Decimal('500.00'))
        record = period.records.get()
        with self.assertRaises(ValueError):
            deposits.record_recovery(record, user=self.owner)

    def test_the_money_rounds_half_up_like_payroll(self):
        self.assertEqual(deposits._money(Decimal('0.005')), Decimal('0.01'))
        self.assertEqual(deposits._money(Decimal('0.015')), Decimal('0.02'))

    def test_a_non_numeric_staff_id_is_a_404_not_a_500(self):
        response = self.client_for(self.owner).get('/api/payroll/deposits/abc/')
        self.assertEqual(response.status_code, 404)

    def test_totals_are_strings_not_floats(self):
        """A float in a payroll payload undoes the whole point of Decimal."""
        self.profile(self.anita, '100.00', deposit_total=Decimal('5000.00'),
                     deposit_weekly=Decimal('500.00'))
        deposits.record_agreement(self.anita, Decimal('5000.00'), user=self.owner)
        self.session(self.anita, 1, 9, 17)
        self.generate()
        period = PayrollPeriod.objects.get()
        response = self.client_for(self.owner).get(
            reverse('payroll-period-detail', args=[period.id]))
        totals = response.data['totals']
        for key in ('total_gross', 'total_deposit_recovered',
                    'total_deposit_unrecovered', 'total_net'):
            self.assertIsInstance(totals[key], str, key)

    def test_approval_refreshes_stale_draft_balances(self):
        """Two weeks drafted, then approved in turn: the second must not lie.

        The second draft was calculated when 5,000 was owed. Approving the first
        takes it to 4,500, so the second record's stored "owed before" would
        otherwise still read 5,000 -- an obligation that was never true at the
        moment its money moved.
        """
        self.profile(self.anita, '100.00', deposit_total=Decimal('5000.00'),
                     deposit_weekly=Decimal('500.00'))
        deposits.record_agreement(self.anita, Decimal('5000.00'), user=self.owner)
        self.session(self.anita, 1, 9, 17)
        self.session(self.anita, 8, 9, 17, month=9)

        first = self.generate()
        second = services.generate(date(2026, 9, 8), user=self.owner)
        self.assertEqual(second.records.get().deposit_balance_before,
                         Decimal('5000.00'))

        services.approve(first, user=self.owner)
        services.approve(second, user=self.owner)

        record = second.records.get()
        self.assertEqual(record.deposit_balance_before, Decimal('4500.00'))
        self.assertEqual(record.deposit_balance_after, Decimal('4000.00'))
        self.assertEqual(deposits.deposit_state(self.anita)['remaining'],
                         Decimal('4000.00'))


class ConcurrentRecoveryTests(TransactionTestCase):
    """Two weeks approved at the same instant must not over-recover.

    The one test in this file that uses real threads and real transactions.
    Everything else runs inside a single test transaction, where two "concurrent"
    approvals are just two sequential calls -- which is exactly why the defect
    this guards against survived a full suite of passing tests.

    The defect: approve() locks the PayrollPeriod, so two DIFFERENT weeks take
    two different locks and never block each other. Both read the same remaining
    obligation, both write a recovery against it, and a staff member owing 800
    has 1,000 taken. The fix locks the PERSON inside record_recovery, so any two
    recoveries for the same staff member serialise whatever week they belong to.
    """

    def setUp(self):
        connection.set_schema_to_public()
        self.tenant = BoutiqueTenant(
            schema_name='conc_dep', owner_email='owner@conc.test',
            name='Concurrency Atelier', timezone='Asia/Kolkata')
        self.tenant.save()
        with schema_context('conc_dep'):
            self.owner = User.objects.create_user(
                username='owner@conc.test', email='owner@conc.test',
                password='ownerpw12345')
            self.staff = Tailor.objects.create(
                name='Racer', specialty='Stitching', role='Tailor')
            StaffProfile.objects.create(
                staff=self.staff, hourly_rate=Decimal('100.00'),
                deposit_total=Decimal('800.00'), deposit_weekly=Decimal('500.00'))
            deposits.record_agreement(self.staff, Decimal('800.00'), user=self.owner)
            self.periods = [self._week(d) for d in
                            (date(2026, 8, 31), date(2026, 9, 7))]

    def tearDown(self):
        connection.set_schema_to_public()
        with connection.cursor() as c:
            c.execute('DROP SCHEMA IF EXISTS "conc_dep" CASCADE')
        BoutiqueTenant.objects.filter(schema_name='conc_dep').delete()

    def _week(self, start):
        period = PayrollPeriod.objects.create(
            period_start=start, period_end=start + timedelta(days=6))
        PayrollRecord.objects.create(
            period=period, staff=self.staff, staff_name_snapshot='Racer',
            hourly_rate_snapshot=Decimal('100.00'),
            worked_minutes=480, regular_minutes=480,
            gross_earnings=Decimal('800.00'),
            deposit_scheduled=Decimal('500.00'),
            deposit_recovered=Decimal('500.00'),
            deposit_balance_before=Decimal('800.00'),
            deposit_balance_after=Decimal('300.00'),
            net_before_other_deductions=Decimal('300.00'))
        return period

    def test_two_weeks_approved_at_once_never_over_recover(self):
        import threading

        barrier = threading.Barrier(2)
        errors = []

        def approve(period_id):
            try:
                with schema_context('conc_dep'):
                    period = PayrollPeriod.objects.get(pk=period_id)
                    barrier.wait(timeout=10)
                    services.approve(period, user=self.owner)
            except Exception as exc:            # noqa: BLE001 - recorded, asserted below
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=approve, args=(p.pk,))
                   for p in self.periods]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        with schema_context('conc_dep'):
            state = deposits.deposit_state(self.staff)
            taken = sum(
                e.amount for e in StaffLedgerEntry.objects.filter(
                    entry_type='DEPOSIT_RECOVERY'))

        # The whole point: never more than was owed, however the race resolved.
        self.assertLessEqual(taken, Decimal('800.00'),
                             f'over-recovered: {taken} against 800.00 owed')
        self.assertEqual(state['over_recovered'], Decimal('0.00'))
        self.assertLessEqual(state['recovered'], state['agreed'])


class DepositListIsLedgerDrivenTests(PayrollTestCase):
    def test_deleting_the_employment_terms_does_not_hide_an_obligation(self):
        """The ledger decides who owes money, not the profile.

        Keyed on StaffProfile, this list would have quietly dropped anybody
        whose employment terms were deleted -- while the ledger went on saying
        they owed 5,000.
        """
        profile = self.profile(self.anita, '100.00',
                               deposit_total=Decimal('5000.00'),
                               deposit_weekly=Decimal('500.00'))
        deposits.record_agreement(self.anita, Decimal('5000.00'), user=self.owner)
        profile.delete()

        response = self.client_for(self.owner).get(reverse('payroll-deposit-list'))
        self.assertEqual(response.status_code, 200)
        names = [row['staff_name'] for row in response.data]
        self.assertIn('Anita', names)
        self.assertEqual(response.data[0]['remaining'], '5000.00')

    def test_staff_with_no_deposit_are_not_listed(self):
        self.profile(self.anita, '100.00')
        response = self.client_for(self.owner).get(reverse('payroll-deposit-list'))
        self.assertEqual(response.data, [])


# =============================================================================
# PHASE 6 -- advances, net payable, payouts
# =============================================================================

from . import advances, payouts  # noqa: E402
from .models import Payout, StaffAdvance  # noqa: E402


class AdvanceTestCase(PayrollTestCase):
    """The Phase 5 fixtures plus an advance helper."""

    def advance(self, tailor, amount, weekly='0.00', day=date(2026, 9, 2), reason='Emergency'):
        return advances.issue(
            tailor, Decimal(amount), user=self.owner, issued_on=day,
            reason=reason, weekly_recovery=Decimal(weekly))

    def deposit(self, tailor, total='5000.00', weekly='500.00', rate='100.00'):
        profile = self.profile(tailor, rate, deposit_total=Decimal(total),
                               deposit_weekly=Decimal(weekly))
        if Decimal(total) > 0:
            deposits.record_agreement(tailor, Decimal(total), user=self.owner)
        return profile

    def full_week(self, tailor):
        """42h 30m = 2,550 minutes, the brief's figure."""
        for d, e in ((1, 17), (2, 17), (3, 17), (4, 17)):
            self.session(tailor, d, 9, e)                   # 4 x 480
        self.session(tailor, 5, 9, 17, end_minute=30)       # 510
        self.session(tailor, 6, 9, 11)                       # 120


class AdvanceLedgerTests(AdvanceTestCase):
    def test_issuing_an_advance_writes_the_obligation(self):
        adv = self.advance(self.anita, '5000.00', weekly='1000.00')
        self.assertEqual(adv.amount, Decimal('5000.00'))
        entry = StaffLedgerEntry.objects.get(advance=adv)
        self.assertEqual(entry.entry_type, 'ADVANCE_ISSUED')
        self.assertEqual(entry.amount, Decimal('5000.00'))
        self.assertEqual(advances.outstanding_for(adv), Decimal('5000.00'))

    def test_a_negative_advance_is_refused(self):
        with self.assertRaises(advances.AdvanceError):
            self.advance(self.anita, '-100.00')
        self.assertEqual(StaffAdvance.objects.count(), 0)

    def test_a_zero_advance_is_refused(self):
        with self.assertRaises(advances.AdvanceError):
            self.advance(self.anita, '0.00')

    def test_the_database_refuses_a_zero_advance(self):
        with self.assertRaises(IntegrityError):
            StaffAdvance.objects.create(
                staff=self.anita, staff_name_snapshot='Anita',
                amount=Decimal('0.00'), issued_on=date(2026, 9, 2))

    def test_a_negative_amount_is_refused_over_the_api(self):
        response = self.client_for(self.owner).post(
            reverse('payroll-advance-list'),
            {'staff': self.anita.id, 'amount': '-50.00', 'issued_on': '2026-09-02'},
            format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(StaffAdvance.objects.count(), 0)

    def test_outstanding_is_derived_from_the_ledger(self):
        adv = self.advance(self.anita, '5000.00')
        rec = PayrollRecord.objects.create(
            period=PayrollPeriod.objects.create(
                period_start=date(2020, 1, 6), period_end=date(2020, 1, 12)),
            staff=self.anita, staff_name_snapshot='Anita',
            worked_minutes=0, regular_minutes=0)
        StaffLedgerEntry.objects.create(
            staff=self.anita, staff_name_snapshot='Anita',
            entry_type='ADVANCE_RECOVERY', amount=Decimal('1000.00'),
            advance=adv, payroll_record=rec)
        self.assertEqual(advances.recovered_for(adv), Decimal('1000.00'))
        self.assertEqual(advances.outstanding_for(adv), Decimal('4000.00'))

    def test_outstanding_never_goes_negative(self):
        adv = self.advance(self.anita, '100.00')
        rec = PayrollRecord.objects.create(
            period=PayrollPeriod.objects.create(
                period_start=date(2020, 1, 6), period_end=date(2020, 1, 12)),
            staff=self.anita, staff_name_snapshot='Anita',
            worked_minutes=0, regular_minutes=0)
        StaffLedgerEntry.objects.create(
            staff=self.anita, staff_name_snapshot='Anita',
            entry_type='ADVANCE_RECOVERY', amount=Decimal('500.00'),
            advance=adv, payroll_record=rec)
        self.assertEqual(advances.outstanding_for(adv), Decimal('0.00'))

    def test_the_advance_is_traceable(self):
        adv = self.advance(self.anita, '5000.00', reason='Medical emergency')
        self.assertEqual(adv.created_by, self.owner)
        self.assertEqual(adv.reason, 'Medical emergency')
        self.assertEqual(adv.issued_on, date(2026, 9, 2))
        self.assertIsNotNone(adv.created_at)

    def test_an_advance_row_must_name_its_advance(self):
        with self.assertRaises(IntegrityError):
            StaffLedgerEntry.objects.create(
                staff=self.anita, staff_name_snapshot='Anita',
                entry_type='ADVANCE_ISSUED', amount=Decimal('100.00'))


class AdvanceCancellationTests(AdvanceTestCase):
    def test_cancelling_reverses_without_deleting(self):
        adv = self.advance(self.anita, '5000.00')
        advances.cancel(adv, user=self.owner, reason='Typed 5000 for 500')
        adv.refresh_from_db()
        self.assertEqual(adv.status, 'CANCELLED')
        self.assertEqual(advances.outstanding_for(adv), Decimal('0.00'))
        types = list(StaffLedgerEntry.objects.filter(advance=adv)
                     .order_by('created_at').values_list('entry_type', flat=True))
        self.assertEqual(types, ['ADVANCE_ISSUED', 'ADVANCE_CANCELLED'])

    def test_cancelling_needs_a_reason(self):
        adv = self.advance(self.anita, '5000.00')
        with self.assertRaises(advances.AdvanceError):
            advances.cancel(adv, user=self.owner, reason='  ')

    def test_a_partly_recovered_advance_cannot_be_cancelled(self):
        self.deposit(self.anita, total='0.00', weekly='0.00')
        adv = self.advance(self.anita, '5000.00', weekly='1000.00')
        self.session(self.anita, 1, 9, 17)
        services.approve(self.generate(), user=self.owner)
        self.assertEqual(advances.recovered_for(adv), Decimal('800.00'))
        with self.assertRaises(advances.AdvanceError):
            advances.cancel(adv, user=self.owner, reason='Too late')

    def test_a_cancelled_advance_is_not_recovered(self):
        self.deposit(self.anita, total='0.00', weekly='0.00')
        adv = self.advance(self.anita, '5000.00', weekly='1000.00')
        advances.cancel(adv, user=self.owner, reason='Error')
        self.session(self.anita, 1, 9, 17)
        record = self.generate().records.get()
        self.assertEqual(record.advance_recovered, Decimal('0.00'))
        self.assertEqual(record.net_payable, Decimal('800.00'))

    def test_there_is_no_delete_endpoint(self):
        adv = self.advance(self.anita, '5000.00')
        response = self.client_for(self.owner).delete(
            reverse('payroll-advance-detail', args=[adv.id]))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(StaffAdvance.objects.count(), 1)


class DeductionOrderTests(AdvanceTestCase):
    """The mandatory worked examples. Deposit first, advance second, net >= 0."""

    def test_the_headline_example(self):
        """4,250 gross, 500 deposit, 1,000 advance -> 2,750 net."""
        self.deposit(self.anita)
        self.advance(self.anita, '5000.00', weekly='1000.00')
        self.full_week(self.anita)
        r = self.generate().records.get()
        self.assertEqual(r.gross_earnings, Decimal('4250.00'))
        self.assertEqual(r.deposit_recovered, Decimal('500.00'))
        self.assertEqual(r.advance_recovered, Decimal('1000.00'))
        self.assertEqual(r.net_payable, Decimal('2750.00'))
        self.assertEqual(r.net_before_other_deductions, Decimal('3750.00'))

    def test_no_deposit(self):
        self.deposit(self.anita, total='0.00', weekly='0.00')
        self.advance(self.anita, '5000.00', weekly='1000.00')
        self.full_week(self.anita)
        r = self.generate().records.get()
        self.assertEqual(r.deposit_recovered, Decimal('0.00'))
        self.assertEqual(r.advance_recovered, Decimal('1000.00'))
        self.assertEqual(r.net_payable, Decimal('3250.00'))

    def test_no_advance(self):
        self.deposit(self.anita)
        self.full_week(self.anita)
        r = self.generate().records.get()
        self.assertEqual(r.deposit_recovered, Decimal('500.00'))
        self.assertEqual(r.advance_recovered, Decimal('0.00'))
        self.assertEqual(r.net_payable, Decimal('3750.00'))

    def test_low_gross_deposit_takes_everything_advance_gets_nothing(self):
        """300 gross, 300 deposit due, 500 advance due -> advance 0, net 0."""
        self.deposit(self.anita, weekly='300.00')
        self.advance(self.anita, '5000.00', weekly='500.00')
        self.session(self.anita, 1, 9, 12)   # 180 min = 300.00
        r = self.generate().records.get()
        self.assertEqual(r.gross_earnings, Decimal('300.00'))
        self.assertEqual(r.deposit_recovered, Decimal('300.00'))
        self.assertEqual(r.advance_recovered, Decimal('0.00'))
        self.assertEqual(r.advance_unrecovered, Decimal('500.00'))
        self.assertEqual(r.net_payable, Decimal('0.00'))

    def test_partial_advance_from_what_the_deposit_left(self):
        """1,000 gross, 200 deposit, 1,000 advance due -> advance 800, net 0."""
        self.deposit(self.anita, weekly='200.00')
        self.advance(self.anita, '5000.00', weekly='1000.00')
        self.session(self.anita, 1, 9, 19)   # 600 min = 1000.00
        r = self.generate().records.get()
        self.assertEqual(r.deposit_recovered, Decimal('200.00'))
        self.assertEqual(r.advance_scheduled, Decimal('1000.00'))
        self.assertEqual(r.advance_recovered, Decimal('800.00'))
        self.assertEqual(r.advance_unrecovered, Decimal('200.00'))
        self.assertEqual(r.net_payable, Decimal('0.00'))

    def test_the_brief_section_44_example(self):
        """500 gross, 300 deposit, 500 advance -> deposit 300, advance 200, net 0."""
        self.deposit(self.anita, weekly='300.00')
        self.advance(self.anita, '5000.00', weekly='500.00')
        self.session(self.anita, 1, 9, 14)   # 300 min = 500.00
        r = self.generate().records.get()
        self.assertEqual(r.deposit_recovered, Decimal('300.00'))
        self.assertEqual(r.advance_recovered, Decimal('200.00'))
        self.assertEqual(r.net_payable, Decimal('0.00'))
        self.assertEqual(r.advance_balance_after, Decimal('4800.00'))

    def test_the_brief_section_47_example(self):
        """10,000 owed, 2,000 weekly, 1,500 gross, 500 deposit -> advance 1,000, missed 1,000."""
        self.deposit(self.anita)
        self.advance(self.anita, '10000.00', weekly='2000.00')
        self.session(self.anita, 1, 8, 23)   # 900 min = 1500.00
        r = self.generate().records.get()
        self.assertEqual(r.gross_earnings, Decimal('1500.00'))
        self.assertEqual(r.deposit_recovered, Decimal('500.00'))
        self.assertEqual(r.advance_recovered, Decimal('1000.00'))
        self.assertEqual(r.advance_unrecovered, Decimal('1000.00'))
        self.assertEqual(r.net_payable, Decimal('0.00'))

    def test_zero_gross_recovers_nothing_anywhere(self):
        self.deposit(self.anita)
        self.advance(self.anita, '5000.00', weekly='1000.00')
        AttendanceSession.objects.create(
            staff=self.anita, date=date(2026, 9, 1), check_in=self.at(1, 9, month=9))
        r = self.generate().records.get()
        self.assertEqual(r.gross_earnings, Decimal('0.00'))
        self.assertEqual(r.deposit_recovered, Decimal('0.00'))
        self.assertEqual(r.advance_recovered, Decimal('0.00'))
        self.assertEqual(r.net_payable, Decimal('0.00'))

    def test_net_payable_is_never_negative_at_the_database(self):
        self.deposit(self.anita)
        self.session(self.anita, 1, 9, 17)
        record = self.generate().records.get()
        with self.assertRaises(IntegrityError):
            PayrollRecord.objects.filter(pk=record.pk).update(
                net_payable=Decimal('-1.00'))

    def test_the_phase_4_gross_and_phase_5_deposit_are_unchanged(self):
        """The advance layer only ever reads what the earlier layers left."""
        self.deposit(self.balan)
        self.deposit(self.anita)
        self.advance(self.anita, '5000.00', weekly='1000.00')
        self.full_week(self.anita)
        self.full_week(self.balan)
        by = {r.staff_name_snapshot: r for r in self.generate().records.all()}
        for name in ('Anita', 'Balan'):
            self.assertEqual(by[name].gross_earnings, Decimal('4250.00'))
            self.assertEqual(by[name].deposit_recovered, Decimal('500.00'))
            self.assertEqual(by[name].net_before_other_deductions, Decimal('3750.00'))
        self.assertEqual(by['Balan'].net_payable, Decimal('3750.00'))
        self.assertEqual(by['Anita'].net_payable, Decimal('2750.00'))


class MultipleAdvanceTests(AdvanceTestCase):
    def test_oldest_advance_is_recovered_first(self):
        """A 2,000 (Sep 1), B 3,000 (Sep 10); 1,500 available -> A 1,500, B 0."""
        self.deposit(self.anita, total='0.00', weekly='0.00')
        a = self.advance(self.anita, '2000.00', weekly='1500.00', day=date(2026, 9, 1))
        b = self.advance(self.anita, '3000.00', weekly='1500.00', day=date(2026, 9, 10))
        self.session(self.anita, 1, 8, 23)   # 1500.00 gross
        r = self.generate().records.get()
        self.assertEqual(r.advance_recovered_from_id, a.id)
        self.assertEqual(r.advance_recovered, Decimal('1500.00'))
        self.assertEqual(advances.outstanding_for(b), Decimal('3000.00'))

    def test_a_is_finished_before_b_begins(self):
        self.deposit(self.anita, total='0.00', weekly='0.00')
        a = self.advance(self.anita, '2000.00', weekly='1500.00', day=date(2026, 9, 1))
        b = self.advance(self.anita, '3000.00', weekly='1500.00', day=date(2026, 9, 10))

        self.session(self.anita, 1, 8, 23)
        services.approve(self.generate(), user=self.owner)
        self.assertEqual(advances.outstanding_for(a), Decimal('500.00'))

        self.session(self.anita, 8, 8, 23, month=9)
        second = services.generate(date(2026, 9, 8), user=self.owner)
        r = second.records.get()
        # Only A's 500 remainder this week; B is untouched until A is done.
        self.assertEqual(r.advance_recovered_from_id, a.id)
        self.assertEqual(r.advance_recovered, Decimal('500.00'))
        services.approve(second, user=self.owner)
        self.assertEqual(advances.outstanding_for(a), Decimal('0.00'))
        self.assertEqual(advances.outstanding_for(b), Decimal('3000.00'))

        self.session(self.anita, 15, 8, 23, month=9)
        third = services.generate(date(2026, 9, 15), user=self.owner)
        self.assertEqual(third.records.get().advance_recovered_from_id, b.id)
        self.assertEqual(third.records.get().advance_recovered, Decimal('1500.00'))

    def test_recovery_order_is_by_issue_date_not_creation_order(self):
        self.deposit(self.anita, total='0.00', weekly='0.00')
        later = self.advance(self.anita, '3000.00', weekly='500.00', day=date(2026, 9, 10))
        earlier = self.advance(self.anita, '2000.00', weekly='500.00', day=date(2026, 9, 1))
        self.session(self.anita, 1, 9, 17)
        r = self.generate().records.get()
        self.assertEqual(r.advance_recovered_from_id, earlier.id)
        self.assertNotEqual(r.advance_recovered_from_id, later.id)


class AdvanceTermChangeTests(AdvanceTestCase):
    def test_a_changed_weekly_rule_applies_only_to_future_weeks(self):
        self.deposit(self.anita, total='0.00', weekly='0.00')
        adv = self.advance(self.anita, '5000.00', weekly='1000.00')
        self.session(self.anita, 1, 9, 17)
        first = self.generate()
        services.approve(first, user=self.owner)
        self.assertEqual(first.records.get().advance_recovered, Decimal('800.00'))

        advances.set_weekly_recovery(adv, Decimal('500.00'), user=self.owner)

        first.records.get().refresh_from_db()
        self.assertEqual(first.records.get().advance_recovered, Decimal('800.00'))
        self.session(self.anita, 8, 9, 17, month=9)
        second = services.generate(date(2026, 9, 8), user=self.owner)
        self.assertEqual(second.records.get().advance_recovered, Decimal('500.00'))

    def test_only_the_weekly_rule_is_editable_over_the_api(self):
        adv = self.advance(self.anita, '5000.00', weekly='1000.00')
        response = self.client_for(self.owner).patch(
            reverse('payroll-advance-detail', args=[adv.id]),
            {'amount': '1.00', 'weekly_recovery': '250.00', 'issued_on': '2001-01-01'},
            format='json')
        self.assertEqual(response.status_code, 200, response.data)
        adv.refresh_from_db()
        self.assertEqual(adv.amount, Decimal('5000.00'))
        self.assertEqual(adv.issued_on, date(2026, 9, 2))
        self.assertEqual(adv.weekly_recovery, Decimal('250.00'))


class AdvanceImmutabilityTests(AdvanceTestCase):
    def setUp(self):
        super().setUp()
        self.p = self.deposit(self.anita)
        self.adv = self.advance(self.anita, '5000.00', weekly='1000.00')
        self.full_week(self.anita)
        self.period = self.generate()
        services.approve(self.period, user=self.owner)
        self.record = self.period.records.get()
        self.before = (self.record.gross_earnings, self.record.deposit_recovered,
                       self.record.advance_recovered, self.record.net_payable,
                       self.record.hourly_rate_snapshot, self.record.worked_minutes)

    def _unchanged(self):
        self.record.refresh_from_db()
        self.assertEqual(
            (self.record.gross_earnings, self.record.deposit_recovered,
             self.record.advance_recovered, self.record.net_payable,
             self.record.hourly_rate_snapshot, self.record.worked_minutes),
            self.before)

    def test_changing_advance_terms_does_not_move_approved_payroll(self):
        advances.set_weekly_recovery(self.adv, Decimal('1.00'), user=self.owner)
        self._unchanged()

    def test_changing_the_profile_does_not_move_approved_payroll(self):
        self.p.hourly_rate = Decimal('999.00')
        self.p.deposit_weekly = Decimal('1.00')
        self.p.save()
        self._unchanged()

    def test_changing_deposit_terms_does_not_move_approved_payroll(self):
        deposits.record_agreement(self.anita, Decimal('100.00'), user=self.owner)
        self._unchanged()

    def test_correcting_attendance_does_not_move_approved_payroll(self):
        session = AttendanceSession.objects.filter(staff=self.anita).first()
        self.client_for(self.owner).post(
            reverse('staff-attendance-correct', args=[session.id]),
            {'check_in': '2026-09-01T05:00:00', 'check_out': '2026-09-01T23:00:00',
             'reason': 'must not reach approved payroll'}, format='json')
        self._unchanged()

    def test_the_ledger_names_the_payroll_and_the_advance(self):
        entry = StaffLedgerEntry.objects.get(entry_type='ADVANCE_RECOVERY')
        self.assertEqual(entry.payroll_record_id, self.record.id)
        self.assertEqual(entry.advance_id, self.adv.id)
        self.assertEqual(entry.balance_before, Decimal('5000.00'))
        self.assertEqual(entry.balance_after, Decimal('4000.00'))

    def test_history_survives_deleting_the_staff_member(self):
        self.anita.delete()
        self.record.refresh_from_db()
        self.assertIsNone(self.record.staff)
        self.assertEqual(self.record.staff_name_snapshot, 'Anita')
        self.assertEqual(self.record.net_payable, Decimal('2750.00'))
        entry = StaffLedgerEntry.objects.get(entry_type='ADVANCE_RECOVERY')
        self.assertIsNone(entry.staff)
        self.assertEqual(entry.staff_name_snapshot, 'Anita')
        self.adv.refresh_from_db()
        self.assertEqual(self.adv.staff_name_snapshot, 'Anita')


class AdvanceIdempotencyTests(AdvanceTestCase):
    def setUp(self):
        super().setUp()
        self.deposit(self.anita, total='0.00', weekly='0.00')
        self.adv = self.advance(self.anita, '5000.00', weekly='1000.00')
        self.session(self.anita, 1, 9, 17)

    def _recoveries(self):
        return StaffLedgerEntry.objects.filter(entry_type='ADVANCE_RECOVERY').count()

    def test_drafting_repeatedly_moves_no_money(self):
        for _ in range(4):
            self.generate()
        self.assertEqual(self._recoveries(), 0)

    def test_approving_writes_exactly_one_recovery(self):
        services.approve(self.generate(), user=self.owner)
        self.assertEqual(self._recoveries(), 1)

    def test_a_second_approval_creates_no_second_recovery(self):
        period = self.generate()
        services.approve(period, user=self.owner)
        with self.assertRaises(services.PayrollError):
            services.approve(period, user=self.owner)
        self.assertEqual(self._recoveries(), 1)
        self.assertEqual(advances.recovered_for(self.adv), Decimal('800.00'))

    def test_the_database_refuses_two_recoveries_for_one_payroll(self):
        period = self.generate()
        services.approve(period, user=self.owner)
        with self.assertRaises(IntegrityError):
            StaffLedgerEntry.objects.create(
                staff=self.anita, staff_name_snapshot='Anita',
                entry_type='ADVANCE_RECOVERY', amount=Decimal('1.00'),
                advance=self.adv, payroll_record=period.records.get())

    def test_a_stale_draft_is_refused_not_over_recovered(self):
        period = self.generate()
        # Someone else took most of it in the meantime.
        StaffLedgerEntry.objects.create(
            staff=self.anita, staff_name_snapshot='Anita',
            entry_type='ADVANCE_RECOVERY', amount=Decimal('4900.00'),
            advance=self.adv,
            payroll_record=PayrollRecord.objects.create(
                period=PayrollPeriod.objects.create(
                    period_start=date(2019, 1, 7), period_end=date(2019, 1, 13)),
                staff=self.anita, staff_name_snapshot='Anita',
                worked_minutes=0, regular_minutes=0))
        with self.assertRaises(services.PayrollError):
            services.approve(period, user=self.owner)
        period.refresh_from_db()
        self.assertEqual(period.status, 'DRAFT')
        self.assertEqual(self._recoveries(), 1)


class PayoutTests(AdvanceTestCase):
    def setUp(self):
        super().setUp()
        self.deposit(self.anita)
        self.advance(self.anita, '5000.00', weekly='1000.00')
        self.full_week(self.anita)
        self.period = self.generate()
        services.approve(self.period, user=self.owner)
        self.record = self.period.records.get()

    def test_marking_paid_records_the_approved_net_exactly(self):
        payout = payouts.record_payout(
            self.record, user=self.owner, method='BANK_TRANSFER', reference='UTR123')
        self.assertEqual(payout.amount, Decimal('2750.00'))
        self.assertEqual(payout.amount, self.record.net_payable)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, 'PAID')
        self.assertIsNotNone(self.record.paid_at)
        self.assertEqual(payout.paid_by, self.owner)
        self.assertEqual(payout.reference, 'UTR123')

    def test_the_amount_is_never_taken_from_the_client(self):
        response = self.client_for(self.owner).post(
            reverse('payroll-record-payout', args=[self.record.id]),
            {'method': 'cash', 'amount': '1.00', 'reference': 'V-1'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Payout.objects.get().amount, Decimal('2750.00'))

    def test_a_draft_cannot_be_paid(self):
        self.session(self.balan, 1, 9, 17)
        self.deposit(self.balan, total='0.00', weekly='0.00')
        draft = services.generate(date(2026, 9, 8), user=self.owner)
        self.session(self.balan, 8, 9, 17, month=9)
        draft = services.generate(date(2026, 9, 8), user=self.owner)
        with self.assertRaises(payouts.PayoutError):
            payouts.record_payout(draft.records.get(), user=self.owner, method='CASH')
        self.assertEqual(Payout.objects.count(), 0)

    def test_paying_twice_is_refused(self):
        payouts.record_payout(self.record, user=self.owner, method='CASH')
        with self.assertRaises(payouts.PayoutError):
            payouts.record_payout(self.record, user=self.owner, method='CASH')
        self.assertEqual(Payout.objects.count(), 1)

    def test_three_mark_paid_requests_make_one_payout(self):
        owner = self.client_for(self.owner)
        url = reverse('payroll-record-payout', args=[self.record.id])
        codes = [owner.post(url, {'method': 'cash'}, format='json').status_code
                 for _ in range(3)]
        self.assertEqual(codes, [200, 409, 409])
        self.assertEqual(Payout.objects.count(), 1)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, 'PAID')

    def test_the_database_refuses_a_second_payout(self):
        payouts.record_payout(self.record, user=self.owner, method='CASH')
        # Inside its own atomic(): asserting an IntegrityError in a TestCase
        # without one leaves the test transaction aborted, and every query
        # after it -- including teardown -- errors out.
        with self.assertRaises(IntegrityError), transaction.atomic():
            Payout.objects.create(
                payroll_record=self.record, staff=self.anita,
                staff_name_snapshot='Anita', amount=Decimal('1.00'),
                method='CASH', paid_at=timezone.now())

    def test_an_unknown_method_is_refused(self):
        with self.assertRaises(payouts.PayoutError):
            payouts.record_payout(self.record, user=self.owner, method='UPI')

    def test_paid_payroll_is_locked(self):
        payouts.record_payout(self.record, user=self.owner, method='CASH')
        owner = self.client_for(self.owner)
        for url in (reverse('payroll-record-detail', args=[self.record.id]),
                    reverse('payroll-period-detail', args=[self.period.id])):
            self.assertEqual(owner.patch(url, {'net_payable': '1.00'},
                                         format='json').status_code, 405)
            self.assertEqual(owner.delete(url).status_code, 405)
        # Regenerating the week is refused (it is approved) and the record
        # survives untouched.
        with self.assertRaises(services.PayrollError):
            self.generate()
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, 'PAID')
        self.assertEqual(self.record.net_payable, Decimal('2750.00'))

    def test_a_paid_record_cannot_be_deleted_from_under_its_payout(self):
        payouts.record_payout(self.record, user=self.owner, method='CASH')
        with self.assertRaises(Exception):
            self.record.delete()

    def test_payout_and_paid_state_are_atomic(self):
        """If the payout insert fails, the record must not be left PAID.

        A payout row planted by hand leaves status APPROVED. The service's
        insert then collides with it; the collision is contained by the
        service's own savepoint, reported as PayoutError, and the record must
        still read APPROVED -- never PAID-without-a-real-payout.
        """
        with transaction.atomic():
            Payout.objects.create(
                payroll_record=self.record, staff=self.anita,
                staff_name_snapshot='Anita', amount=Decimal('2750.00'),
                method='CASH', paid_at=timezone.now())
        with self.assertRaises(payouts.PayoutError):
            payouts.record_payout(self.record, user=self.owner, method='CASH')
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, 'APPROVED')
        self.assertEqual(Payout.objects.count(), 1)

    def test_the_activity_feed_carries_no_amount(self):
        self.client_for(self.owner).post(
            reverse('payroll-record-payout', args=[self.record.id]),
            {'method': 'bank_transfer'}, format='json')
        for entry in UniversalActivity.objects.all():
            blob = f"{entry.title} {entry.description} {entry.old_value} {entry.new_value}"
            for figure in ('2750', '4250', '1000.00', '500.00'):
                self.assertNotIn(figure, blob)


class Phase6AccessTests(AdvanceTestCase):
    """Owner everything; staff their own reads; Master nothing; nobody else."""

    def setUp(self):
        super().setUp()
        self.deposit(self.anita)
        self.deposit(self.balan)
        self.adv_a = self.advance(self.anita, '5000.00', weekly='1000.00')
        self.adv_b = self.advance(self.balan, '3000.00', weekly='500.00')
        self.full_week(self.anita)
        self.full_week(self.balan)
        self.period = self.generate()
        services.approve(self.period, user=self.owner)
        self.rec_a = self.period.records.get(staff=self.anita)
        self.rec_b = self.period.records.get(staff=self.balan)
        self.master_user = User.objects.create_user(
            username='mira@payroll.test', email='mira@payroll.test',
            password='mirapass12345')
        Tailor.objects.create(name='Mira', specialty='Supervision', role='Master',
                              email='mira@payroll.test', user=self.master_user)

    def test_a_staff_member_reads_their_own_payslip(self):
        response = self.client_for(self.anita_user).get(reverse('payroll-record-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['staff_name_snapshot'], 'Anita')
        self.assertEqual(response.data[0]['net_payable'], '2750.00')

    def test_a_staff_member_cannot_read_a_colleagues_payslip(self):
        response = self.client_for(self.anita_user).get(
            reverse('payroll-record-detail', args=[self.rec_b.id]))
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('Balan', response.content.decode())

    def test_the_staff_filter_is_not_honoured_for_staff(self):
        response = self.client_for(self.anita_user).get(
            reverse('payroll-record-list'), {'staff': self.balan.id})
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['staff_name_snapshot'], 'Anita')

    def test_a_staff_member_reads_only_their_own_advances(self):
        response = self.client_for(self.anita_user).get(reverse('payroll-advance-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([a['staff_name_snapshot'] for a in response.data], ['Anita'])
        detail = self.client_for(self.anita_user).get(
            reverse('payroll-advance-detail', args=[self.adv_b.id]))
        self.assertEqual(detail.status_code, 404)

    def test_a_staff_member_cannot_issue_cancel_or_pay(self):
        anita = self.client_for(self.anita_user)
        self.assertEqual(anita.post(reverse('payroll-advance-list'),
                                    {'staff': self.anita.id, 'amount': '10.00',
                                     'issued_on': '2026-09-02'},
                                    format='json').status_code, 403)
        self.assertEqual(anita.post(reverse('payroll-advance-cancel', args=[self.adv_a.id]),
                                    {'reason': 'x'}, format='json').status_code, 403)
        self.assertEqual(anita.post(reverse('payroll-record-payout', args=[self.rec_a.id]),
                                    {'method': 'cash'}, format='json').status_code, 403)
        self.assertEqual(anita.patch(reverse('payroll-advance-detail', args=[self.adv_a.id]),
                                     {'weekly_recovery': '0.00'},
                                     format='json').status_code, 403)
        self.assertEqual(Payout.objects.count(), 0)

    def test_a_master_sees_no_payroll_and_no_advances(self):
        master = self.client_for(self.master_user)
        for url in (reverse('payroll-record-list'), reverse('payroll-advance-list')):
            response = master.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, [], url)
        for url in (reverse('payroll-period-list'), reverse('payroll-deposit-list')):
            self.assertEqual(master.get(url).status_code, 403, url)

    def test_a_master_cannot_pay_or_issue(self):
        master = self.client_for(self.master_user)
        self.assertEqual(master.post(reverse('payroll-record-payout', args=[self.rec_a.id]),
                                     {'method': 'cash'}, format='json').status_code, 403)
        self.assertEqual(master.post(reverse('payroll-advance-list'),
                                     {'staff': self.anita.id, 'amount': '10.00',
                                      'issued_on': '2026-09-02'},
                                     format='json').status_code, 403)

    def test_no_wage_leaks_to_a_master_anywhere(self):
        master = self.client_for(self.master_user)
        for url in (reverse('payroll-record-list'), reverse('payroll-advance-list'),
                    reverse('payroll-period-list'), reverse('payroll-deposit-list'),
                    reverse('staff-profile-list'), '/api/activities/activities/'):
            body = master.get(url).content.decode()
            for figure in ('2750', '4250', '5000.00', '3000.00', '1000.00'):
                self.assertNotIn(figure, body, url)

    def test_anonymous_is_refused(self):
        anonymous = APIClient()
        anonymous.credentials(HTTP_X_TENANT_ID=self.tenant.schema_name)
        for url in (reverse('payroll-record-list'), reverse('payroll-advance-list')):
            self.assertIn(anonymous.get(url).status_code, (401, 403))


class ConcurrentPhase6Tests(TransactionTestCase):
    """Real threads, real transactions: the races a single test transaction hides."""

    SCHEMA = 'conc_p6'

    def setUp(self):
        connection.set_schema_to_public()
        self.tenant = BoutiqueTenant(
            schema_name=self.SCHEMA, owner_email='owner@conc6.test',
            name='Concurrency Six', timezone='Asia/Kolkata')
        self.tenant.save()
        with schema_context(self.SCHEMA):
            self.owner = User.objects.create_user(
                username='owner@conc6.test', email='owner@conc6.test',
                password='ownerpw12345')
            self.staff = Tailor.objects.create(
                name='Racer', specialty='Stitching', role='Tailor')
            StaffProfile.objects.create(
                staff=self.staff, hourly_rate=Decimal('100.00'))
            self.adv = advances.issue(
                self.staff, Decimal('800.00'), user=self.owner,
                issued_on=date(2026, 9, 1), weekly_recovery=Decimal('500.00'))

    def tearDown(self):
        connection.set_schema_to_public()
        with connection.cursor() as c:
            c.execute(f'DROP SCHEMA IF EXISTS "{self.SCHEMA}" CASCADE')
        BoutiqueTenant.objects.filter(schema_name=self.SCHEMA).delete()

    def _week(self, start, recovered):
        period = PayrollPeriod.objects.create(
            period_start=start, period_end=start + timedelta(days=6))
        return PayrollRecord.objects.create(
            period=period, staff=self.staff, staff_name_snapshot='Racer',
            hourly_rate_snapshot=Decimal('100.00'),
            worked_minutes=480, regular_minutes=480,
            gross_earnings=Decimal('800.00'),
            net_before_other_deductions=Decimal('800.00'),
            advance_recovered_from=self.adv,
            advance_scheduled=recovered, advance_recovered=recovered,
            advance_balance_before=Decimal('800.00'),
            advance_balance_after=Decimal('800.00') - recovered,
            net_payable=Decimal('800.00') - recovered)

    def _run(self, fn, args_list):
        import threading
        barrier = threading.Barrier(len(args_list))
        errors = []

        def worker(args):
            try:
                with schema_context(self.SCHEMA):
                    barrier.wait(timeout=10)
                    fn(*args)
            except Exception as exc:                # noqa: BLE001
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(a,)) for a in args_list]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        return errors

    def test_two_weeks_approved_at_once_never_over_recover_an_advance(self):
        with schema_context(self.SCHEMA):
            periods = [self._week(date(2026, 8, 31), Decimal('500.00')).period,
                       self._week(date(2026, 9, 7), Decimal('500.00')).period]

        def approve(period_id):
            services.approve(PayrollPeriod.objects.get(pk=period_id), user=self.owner)

        self._run(approve, [(p.pk,) for p in periods])

        with schema_context(self.SCHEMA):
            taken = sum(e.amount for e in StaffLedgerEntry.objects.filter(
                entry_type='ADVANCE_RECOVERY'))
            self.assertLessEqual(taken, Decimal('800.00'),
                                 f'over-recovered: {taken} against 800.00 owed')
            self.assertEqual(advances.outstanding_for(self.adv),
                             Decimal('800.00') - taken)

    def test_two_payouts_at_once_produce_one(self):
        with schema_context(self.SCHEMA):
            record = self._week(date(2026, 8, 31), Decimal('500.00'))
            services.approve(record.period, user=self.owner)

        def pay(record_id):
            payouts.record_payout(PayrollRecord.objects.get(pk=record_id),
                                  user=self.owner, method='CASH')

        errors = self._run(pay, [(record.pk,), (record.pk,)])

        with schema_context(self.SCHEMA):
            self.assertEqual(Payout.objects.count(), 1)
            self.assertEqual(PayrollRecord.objects.get(pk=record.pk).status, 'PAID')
        # Exactly one of the two must have been refused.
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], payouts.PayoutError)


class Phase6ReviewFixTests(AdvanceTestCase):
    """Regressions for what the adversarial review found after the tests passed."""

    def test_a_paid_week_still_guards_against_paying_a_session_twice(self):
        """PAID dropped out of already_paid_session_ids. It must not.

        Approve, PAY, then correct the session across the week boundary: the
        next week must not pick the same session up again.
        """
        self.deposit(self.anita, total='0.00', weekly='0.00')
        session = self.session(self.anita, 6, 9, 17)      # Sunday of week 1
        first = self.generate()
        services.approve(first, user=self.owner)
        payouts.record_payout(first.records.get(), user=self.owner, method='CASH')

        session.check_in = self.at(7, 9, month=9)
        session.check_out = self.at(7, 17, month=9)
        session.date = date(2026, 9, 7)
        session.save()

        second = services.generate(date(2026, 9, 7), user=self.owner)
        self.assertEqual(second.records.count(), 0,
                         'a session paid in a PAID week must not be paid again')
        self.assertIn(str(session.id), services.already_paid_session_ids(self.anita))

    def test_weeks_approved_before_phase_6_are_payable_after_the_backfill(self):
        """A pre-existing APPROVED row with net_payable NULL was a dead end."""
        from .migrations import __name__ as _  # noqa: F401  (import guard)
        import importlib
        mod = importlib.import_module('apps.payroll.migrations.0006_backfill_net_payable')
        self.deposit(self.anita)
        self.session(self.anita, 1, 9, 17)
        period = self.generate()
        services.approve(period, user=self.owner)
        record = period.records.get()
        # Simulate a row from before the column existed.
        PayrollRecord.objects.filter(pk=record.pk).update(net_payable=None)
        with self.assertRaises(payouts.PayoutError):
            payouts.record_payout(record, user=self.owner, method='CASH')

        from django.apps import apps as django_apps
        mod.backfill(django_apps, None)
        record.refresh_from_db()
        self.assertEqual(record.net_payable, record.net_before_other_deductions)
        payout = payouts.record_payout(record, user=self.owner, method='CASH')
        self.assertEqual(payout.amount, Decimal('300.00'))   # 800 gross - 500 dep

    def test_backfill_falls_back_to_gross_for_phase_4_era_rows(self):
        import importlib
        mod = importlib.import_module('apps.payroll.migrations.0006_backfill_net_payable')
        self.deposit(self.anita, total='0.00', weekly='0.00')
        self.session(self.anita, 1, 9, 17)
        period = self.generate()
        services.approve(period, user=self.owner)
        record = period.records.get()
        PayrollRecord.objects.filter(pk=record.pk).update(
            net_payable=None, net_before_other_deductions=None)
        from django.apps import apps as django_apps
        mod.backfill(django_apps, None)
        record.refresh_from_db()
        self.assertEqual(record.net_payable, Decimal('800.00'))

    def test_a_second_cancel_is_refused_by_the_database(self):
        adv = self.advance(self.anita, '5000.00')
        advances.cancel(adv, user=self.owner, reason='Error')
        with self.assertRaises(IntegrityError):
            StaffLedgerEntry.objects.create(
                staff=self.anita, staff_name_snapshot='Anita',
                entry_type='ADVANCE_CANCELLED', amount=Decimal('1.00'),
                advance=adv)

    def test_a_cancelled_advance_is_refused_at_recovery_even_if_the_draft_predates_it(self):
        """The draft was calculated against a live advance; it was cancelled since."""
        self.deposit(self.anita, total='0.00', weekly='0.00')
        adv = self.advance(self.anita, '5000.00', weekly='1000.00')
        self.session(self.anita, 1, 9, 17)
        period = self.generate()
        self.assertEqual(period.records.get().advance_recovered, Decimal('800.00'))
        advances.cancel(adv, user=self.owner, reason='Entered in error')
        with self.assertRaises(services.PayrollError):
            services.approve(period, user=self.owner)
        period.refresh_from_db()
        self.assertEqual(period.status, 'DRAFT')
        self.assertEqual(StaffLedgerEntry.objects.filter(
            entry_type='ADVANCE_RECOVERY').count(), 0)

    def test_a_race_loser_gets_a_conflict_not_a_server_error(self):
        """AdvanceError inside approve() must surface as 409, not 500."""
        self.deposit(self.anita, total='0.00', weekly='0.00')
        adv = self.advance(self.anita, '5000.00', weekly='1000.00')
        self.session(self.anita, 1, 9, 17)
        period = self.generate()
        advances.cancel(adv, user=self.owner, reason='Entered in error')
        response = self.client_for(self.owner).post(
            reverse('payroll-period-approve', args=[period.id]), {}, format='json')
        self.assertEqual(response.status_code, 409, response.data)
        self.assertIn('cancelled', response.data['error'])

    def test_a_parked_oldest_advance_does_not_freeze_a_newer_one(self):
        """weekly_recovery 0 on advance A must not block recovery of advance B."""
        self.deposit(self.anita, total='0.00', weekly='0.00')
        a = self.advance(self.anita, '2000.00', weekly='0.00', day=date(2026, 9, 1))
        b = self.advance(self.anita, '3000.00', weekly='500.00', day=date(2026, 9, 10))
        self.session(self.anita, 1, 9, 17)
        r = self.generate().records.get()
        self.assertEqual(r.advance_recovered_from_id, b.id)
        self.assertEqual(r.advance_recovered, Decimal('500.00'))
        self.assertEqual(advances.outstanding_for(a), Decimal('2000.00'))

    def test_a_draft_for_a_deleted_person_cannot_be_approved_with_money_on_it(self):
        self.deposit(self.anita)
        self.advance(self.anita, '5000.00', weekly='1000.00')
        self.session(self.anita, 1, 9, 17)
        period = self.generate()
        self.assertGreater(period.records.get().advance_recovered, 0)
        self.anita.delete()               # SET_NULL on the draft record
        with self.assertRaises(services.PayrollError) as caught:
            services.approve(period, user=self.owner)
        self.assertIn('no longer on the roster', str(caught.exception))
        period.refresh_from_db()
        self.assertEqual(period.status, 'DRAFT')
        self.assertEqual(StaffLedgerEntry.objects.filter(
            entry_type__in=['DEPOSIT_RECOVERY', 'ADVANCE_RECOVERY']).count(), 0)

    def test_non_string_payout_fields_are_a_4xx_not_a_500(self):
        self.deposit(self.anita)
        self.session(self.anita, 1, 9, 17)
        period = self.generate()
        services.approve(period, user=self.owner)
        record = period.records.get()
        owner = self.client_for(self.owner)
        url = reverse('payroll-record-payout', args=[record.id])
        for body in ({'method': 1}, {'method': ['cash']}, {'method': 'cash', 'reference': 5},
                     {'method': 'cash', 'note': {'x': 1}}):
            response = owner.post(url, body, format='json')
            self.assertIn(response.status_code, (200, 400, 409), body)
            if response.status_code == 200:
                break  # first valid one pays; later ones must be 409, not 500

    def test_the_activity_feed_names_no_colleague_for_advances(self):
        adv = self.advance(self.anita, '5000.00')
        owner = self.client_for(self.owner)
        owner.post(reverse('payroll-advance-list'),
                   {'staff': self.balan.id, 'amount': '10.00', 'issued_on': '2026-09-02'},
                   format='json')
        owner.post(reverse('payroll-advance-cancel', args=[adv.id]),
                   {'reason': 'x'}, format='json')
        for entry in UniversalActivity.objects.filter(entity_type='StaffAdvance'):
            blob = f"{entry.title} {entry.description} {entry.new_value}"
            self.assertNotIn('Anita', blob)
            self.assertNotIn('Balan', blob)
            self.assertNotIn('5000', blob)


class ConcurrentCancelTests(TransactionTestCase):
    """Cancel racing approval, and cancel racing cancel. Real threads."""

    SCHEMA = 'conc_cancel'

    def setUp(self):
        connection.set_schema_to_public()
        self.tenant = BoutiqueTenant(
            schema_name=self.SCHEMA, owner_email='owner@cc.test',
            name='Cancel Race', timezone='Asia/Kolkata')
        self.tenant.save()
        with schema_context(self.SCHEMA):
            self.owner = User.objects.create_user(
                username='owner@cc.test', email='owner@cc.test', password='pw12345678')
            self.staff = Tailor.objects.create(name='Racer', specialty='S', role='Tailor')
            StaffProfile.objects.create(staff=self.staff, hourly_rate=Decimal('100.00'))
            self.adv = advances.issue(
                self.staff, Decimal('5000.00'), user=self.owner,
                issued_on=date(2026, 9, 1), weekly_recovery=Decimal('1000.00'))
            period = PayrollPeriod.objects.create(
                period_start=date(2026, 8, 31), period_end=date(2026, 9, 6))
            self.record = PayrollRecord.objects.create(
                period=period, staff=self.staff, staff_name_snapshot='Racer',
                hourly_rate_snapshot=Decimal('100.00'),
                worked_minutes=480, regular_minutes=480,
                gross_earnings=Decimal('800.00'),
                net_before_other_deductions=Decimal('800.00'),
                advance_recovered_from=self.adv,
                advance_scheduled=Decimal('800.00'), advance_recovered=Decimal('800.00'),
                advance_balance_before=Decimal('5000.00'),
                advance_balance_after=Decimal('4200.00'),
                net_payable=Decimal('0.00'))

    def tearDown(self):
        connection.set_schema_to_public()
        with connection.cursor() as c:
            c.execute(f'DROP SCHEMA IF EXISTS "{self.SCHEMA}" CASCADE')
        BoutiqueTenant.objects.filter(schema_name=self.SCHEMA).delete()

    def _run(self, jobs):
        import threading
        barrier = threading.Barrier(len(jobs))
        errors = []

        def worker(fn):
            try:
                with schema_context(self.SCHEMA):
                    barrier.wait(timeout=10)
                    fn()
            except Exception as exc:                # noqa: BLE001
                errors.append(exc)
            finally:
                connection.close()

        ts = [threading.Thread(target=worker, args=(j,)) for j in jobs]
        for t in ts: t.start()
        for t in ts: t.join(timeout=30)
        return errors

    def test_cancel_and_approve_at_once_never_leave_a_recovery_on_a_cancelled_advance(self):
        def approve():
            services.approve(PayrollPeriod.objects.get(pk=self.record.period_id),
                             user=self.owner)

        def cancel():
            advances.cancel(StaffAdvance.objects.get(pk=self.adv.pk),
                            user=self.owner, reason='race')

        self._run([approve, cancel])
        with schema_context(self.SCHEMA):
            adv = StaffAdvance.objects.get(pk=self.adv.pk)
            recovered = StaffLedgerEntry.objects.filter(
                entry_type='ADVANCE_RECOVERY', advance=adv).exists()
            # Exactly one of the two outcomes, never both.
            self.assertFalse(adv.is_cancelled and recovered,
                             'a recovery was written against a cancelled advance')
            self.assertTrue(adv.is_cancelled or recovered)

    def test_two_cancels_at_once_write_one_reversal(self):
        def cancel():
            advances.cancel(StaffAdvance.objects.get(pk=self.adv.pk),
                            user=self.owner, reason='double tap')

        errors = self._run([cancel, cancel])
        with schema_context(self.SCHEMA):
            self.assertEqual(StaffLedgerEntry.objects.filter(
                entry_type='ADVANCE_CANCELLED', advance=self.adv).count(), 1)
        self.assertEqual(len(errors), 1)
