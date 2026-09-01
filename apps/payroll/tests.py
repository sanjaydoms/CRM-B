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
from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.activities.models import UniversalActivity
from apps.staff.models import AttendanceSession, StaffProfile
from core.formatting import tenant_timezone
from crm_api.models import Customer, Order, Tailor
from tenants.models import BoutiqueTenant

from . import services
from .models import PayrollPeriod, PayrollRecord

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

    def test_a_master_is_refused_every_payroll_endpoint(self):
        master = self.client_for(self.master_user)
        for url in self._urls():
            self.assertEqual(master.get(url).status_code, 403, url)

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
        tailor = self.client_for(self.anita_user)
        for url in self._urls():
            self.assertEqual(tailor.get(url).status_code, 403, url)

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
        client = self.client_for(user)
        for url in self._urls():
            self.assertEqual(client.get(url).status_code, 403, url)

    def test_an_anonymous_caller_is_refused(self):
        anonymous = APIClient()
        anonymous.credentials(HTTP_X_TENANT_ID=self.tenant.schema_name)
        for url in self._urls():
            self.assertIn(anonymous.get(url).status_code, (401, 403), url)

    def test_no_wage_leaks_in_a_refusal_body(self):
        for client in (self.client_for(self.master_user),
                       self.client_for(self.anita_user)):
            for url in self._urls():
                body = client.get(url).content.decode()
                self.assertNotIn('800.00', body)
                self.assertNotIn('100.00', body)

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
