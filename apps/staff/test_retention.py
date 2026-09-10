"""Phase 9: what must survive somebody leaving.

The test this module exists for is `test_the_hours_behind_a_paid_payslip
_survive_deletion`. Everything else is the perimeter around it.

`AttendanceSession.staff` was CASCADE, so removing a staff member deleted every
shift they had worked -- including the shifts an approved and PAID payslip had
been computed from. The payslip survived, because PayrollRecord is SET_NULL with
its own snapshots, and so did the ledger, the advances, the payouts and the
reviews. Only the evidence went. The boutique kept the payment and lost the
reason for it.

The invariant: once somebody has taken part in a financially or operationally
significant event, deleting their roster row must not erase what is needed to
explain that event.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.payroll.models import (
    PayrollPeriod, PayrollRecord, Payout, StaffAdvance, StaffLedgerEntry,
)
from apps.staff.models import (
    AttendanceSession, StaffPerformanceReview, StaffProfile,
)
from core.formatting import tenant_timezone
from crm_api.models import Tailor
from tenants.models import BoutiqueTenant, Domain

OWNER_EMAIL = 'owner@retain.test'


class RetentionTestCase(TenantTestCase):
    """One boutique, one staff member, and a full financial history."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = OWNER_EMAIL
        tenant.name = 'Retention Atelier'
        return tenant

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        self.owner = User.objects.create_user(
            username=OWNER_EMAIL, email=OWNER_EMAIL, password='ownerpw12345')
        self.staff_user = User.objects.create_user(
            username='asha', email='asha@retain.test', password='ashapw12345')
        self.staff = Tailor.objects.create(
            name='Asha', specialty='Blouses', role='Tailor',
            email='asha@retain.test', user=self.staff_user)
        self.profile = StaffProfile.objects.create(
            staff=self.staff, hourly_rate=Decimal('100.00'))

    def client_for(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Token {token.key}',
                        HTTP_X_TENANT_ID=self.tenant.schema_name)
        return api

    def worked(self, day, hours=8, month=9):
        check_in = timezone.datetime(2026, month, day, 9, 0,
                                     tzinfo=tenant_timezone())
        session = AttendanceSession(
            staff=self.staff, date=date(2026, month, day),
            check_in=check_in, check_out=check_in + timedelta(hours=hours))
        session.minutes = session.duration_minutes()
        session.save()
        return session


class AttendanceSurvivesDeletionTests(RetentionTestCase):

    def test_a_session_outlives_the_roster_row(self):
        session = self.worked(1)
        self.staff.delete()
        session.refresh_from_db()
        self.assertIsNone(session.staff_id)
        self.assertEqual(session.staff_name_snapshot, 'Asha')
        self.assertEqual(session.staff_role_snapshot, 'Tailor')
        self.assertEqual(session.minutes, 480)
        self.assertEqual(session.date, date(2026, 9, 1))

    def test_a_detached_session_still_says_who_it_belonged_to(self):
        """Section 5: the row must answer its own questions after deletion."""
        session = self.worked(1)
        self.staff.delete()
        session.refresh_from_db()
        self.assertEqual(session.staff_label, 'Asha')
        self.assertIn('Asha', str(session))
        self.assertIsNotNone(session.check_in)
        self.assertIsNotNone(session.check_out)

    def test_the_snapshot_is_taken_once_and_never_rewritten(self):
        """Section 8: a rename must not silently rewrite last March."""
        session = self.worked(1)
        self.staff.name = 'Asha Kumari'
        self.staff.role = 'Master'
        self.staff.save(update_fields=['name', 'role'])
        session.note = 'edited later'
        session.save()
        session.refresh_from_db()
        self.assertEqual(session.staff_name_snapshot, 'Asha')
        self.assertEqual(session.staff_role_snapshot, 'Tailor')
        # Still on the roster, so the LIVE name is what the screen shows.
        self.assertEqual(session.staff_label, 'Asha Kumari')

    def test_a_session_with_no_snapshot_does_not_crash(self):
        """Section 21: a row the backfill could not establish stays readable."""
        session = self.worked(1)
        AttendanceSession.objects.filter(pk=session.pk).update(
            staff=None, staff_name_snapshot='', staff_role_snapshot='')
        session.refresh_from_db()
        self.assertEqual(session.staff_label, 'Former staff member')
        self.assertIn('Former staff member', str(session))

    def test_an_open_session_survives_deletion_without_inventing_hours(self):
        """Section 24: deleting while a shift is open must not close it."""
        open_session = AttendanceSession.objects.create(
            staff=self.staff, date=date(2026, 9, 2),
            check_in=timezone.now())
        self.staff.delete()
        open_session.refresh_from_db()
        self.assertIsNone(open_session.staff_id)
        self.assertIsNone(open_session.check_out, 'no hours may be invented')
        self.assertIsNone(open_session.minutes)
        self.assertTrue(open_session.is_open)

    def test_deleting_staff_with_no_history_behaves_normally(self):
        """Section 24: the ordinary case must stay ordinary."""
        spare = Tailor.objects.create(name='Nobody', specialty='X', role='Tailor')
        spare_id = spare.id
        spare.delete()
        self.assertFalse(Tailor.objects.filter(id=spare_id).exists())
        self.assertEqual(AttendanceSession.objects.filter(staff_id=spare_id).count(), 0)


class PayrollTraceabilityTests(RetentionTestCase):
    """Section 6 and 14: the chain must still explain the money."""

    def _approved_payroll(self):
        from apps.payroll import services
        self.worked(1)
        self.worked(2)
        period = services.generate(date(2026, 9, 1), user=self.owner)
        services.approve(period, user=self.owner)
        return period

    def test_the_hours_behind_a_paid_payslip_survive_deletion(self):
        """The reason this module exists."""
        period = self._approved_payroll()
        record = PayrollRecord.objects.get(staff=self.staff)
        frozen_minutes = record.worked_minutes
        frozen_gross = record.gross_earnings
        self.assertGreater(frozen_minutes, 0)

        self.staff.delete()

        record.refresh_from_db()
        self.assertEqual(record.worked_minutes, frozen_minutes)
        self.assertEqual(record.gross_earnings, frozen_gross)
        self.assertEqual(record.staff_name_snapshot, 'Asha')
        self.assertIsNone(record.staff_id)
        # And the evidence is still there to explain it.
        sessions = AttendanceSession.objects.filter(staff_name_snapshot='Asha')
        self.assertEqual(sessions.count(), 2)
        self.assertEqual(sum(s.minutes for s in sessions), frozen_minutes)

    def test_deleting_staff_does_not_recalculate_a_frozen_payroll(self):
        period = self._approved_payroll()
        record = PayrollRecord.objects.get(staff=self.staff)
        before = (record.worked_minutes, record.gross_earnings,
                  record.hourly_rate_snapshot, record.net_payable)
        self.staff.delete()
        record.refresh_from_db()
        self.assertEqual(
            (record.worked_minutes, record.gross_earnings,
             record.hourly_rate_snapshot, record.net_payable), before)

    def test_an_orphaned_session_can_never_be_paid_again(self):
        """Sections 14 and 15, after deletion AND after a re-hire.

        Payroll selects by `staff=<profile>`; a detached session's staff is
        NULL, which matches no profile ever again -- so the hours cannot be
        swept into a new week under a new roster row for the same person.

        Generated for the FOLLOWING week: services.generate refuses to touch an
        approved one at all, which is a stronger guard than this test needs and
        would hide the thing being tested behind it.
        """
        from apps.payroll import services
        self._approved_payroll()
        self.staff.delete()

        rehired = Tailor.objects.create(
            name='Asha', specialty='Blouses', role='Tailor',
            email='asha@retain.test')
        StaffProfile.objects.create(staff=rehired, hourly_rate=Decimal('100.00'))
        self.assertEqual(
            AttendanceSession.objects.filter(staff=rehired).count(), 0)

        # A later week: the orphaned hours are dated inside the approved one, so
        # if the window could ever see them again it would be here.
        period = services.generate(date(2026, 9, 8), user=self.owner)
        fresh = PayrollRecord.objects.filter(staff=rehired).first()
        minutes = fresh.worked_minutes if fresh else 0
        self.assertEqual(minutes, 0,
                         'the old hours were paid to somebody who has gone')

    def test_an_approved_week_cannot_be_regenerated_after_deletion(self):
        """The Phase 4/6 guard must keep holding once staff is detached."""
        from apps.payroll import services
        self._approved_payroll()
        self.staff.delete()
        with self.assertRaises(services.PayrollError):
            services.generate(date(2026, 9, 1), user=self.owner)

    def test_history_from_before_and_after_a_rehire_stays_distinct(self):
        """Section 9: identities must not merge."""
        self.worked(1)
        self.staff.delete()
        rehired = Tailor.objects.create(
            name='Asha', specialty='Blouses', role='Tailor')
        StaffProfile.objects.create(staff=rehired)
        new_session = AttendanceSession(
            staff=rehired, date=date(2026, 10, 1),
            check_in=timezone.datetime(2026, 10, 1, 9, 0, tzinfo=tenant_timezone()))
        new_session.check_out = new_session.check_in + timedelta(hours=8)
        new_session.minutes = new_session.duration_minutes()
        new_session.save()

        self.assertEqual(
            AttendanceSession.objects.filter(staff=rehired).count(), 1,
            'the old employment must not attach to the new roster row')
        self.assertEqual(
            AttendanceSession.objects.filter(staff__isnull=True).count(), 1)


class FinancialHistorySurvivesTests(RetentionTestCase):
    """Section 12: no financial record may be destroyed to fix authorization."""

    def test_ledger_advance_payout_and_review_all_outlive_the_roster_row(self):
        advance = StaffAdvance.objects.create(
            staff=self.staff, staff_name_snapshot='Asha',
            amount=Decimal('2000.00'), issued_on=date(2026, 9, 1))
        # `advance=` is required by ledger_advance_rows_name_their_advance:
        # an advance row that cannot say which advance it belongs to explains
        # nothing, which is exactly the property this module is about.
        entry = StaffLedgerEntry.objects.create(
            staff=self.staff, staff_name_snapshot='Asha', advance=advance,
            entry_type='ADVANCE_ISSUED', amount=Decimal('2000.00'),
            balance_before=Decimal('0.00'), balance_after=Decimal('2000.00'))
        review = StaffPerformanceReview.objects.create(
            staff=self.staff, staff_name_snapshot='Asha', role_snapshot='Tailor',
            period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
            productivity_rating=4, status='FINAL',
            finalised_at=timezone.now(), kpi_snapshot={'frozen': True})

        self.staff.delete()

        for obj, name in ((advance, 'advance'), (entry, 'ledger entry'),
                          (review, 'review')):
            obj.refresh_from_db()
            self.assertIsNone(obj.staff_id, name)
            self.assertEqual(obj.staff_name_snapshot, 'Asha', name)
        self.assertEqual(advance.amount, Decimal('2000.00'))
        self.assertEqual(entry.balance_after, Decimal('2000.00'))
        self.assertEqual(review.role_snapshot, 'Tailor')
        self.assertEqual(review.kpi_snapshot, {'frozen': True})
        self.assertEqual(review.status, 'FINAL')


class HistoricalApiTests(RetentionTestCase):
    """Section 23: a historical endpoint must not 500 because staff is gone."""

    def test_every_history_endpoint_answers_after_deletion(self):
        self.worked(1)
        StaffAdvance.objects.create(
            staff=self.staff, staff_name_snapshot='Asha',
            amount=Decimal('500.00'), issued_on=date(2026, 9, 1))
        StaffPerformanceReview.objects.create(
            staff=self.staff, staff_name_snapshot='Asha', role_snapshot='Tailor',
            period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
            productivity_rating=4)
        self.staff.delete()

        api = self.client_for(self.owner)
        for url, params in (
                (reverse('staff-attendance-list'), {}),
                (reverse('staff-profile-list'), {}),
                (reverse('staff-review-list'), {}),
                (reverse('payroll-record-list'), {}),
                (reverse('payroll-advance-list'), {}),
                (reverse('payroll-deposit-list'), {}),
                (reverse('staff-performance'),
                 {'start': '2026-09-01', 'end': '2026-09-30'}),
        ):
            response = api.get(url, params)
            self.assertLess(response.status_code, 500,
                            f'{url} broke on a detached staff row')

    def test_the_detached_session_is_readable_and_names_its_owner(self):
        self.worked(1)
        self.staff.delete()
        response = self.client_for(self.owner).get(reverse('staff-attendance-list'))
        self.assertEqual(response.status_code, 200)
        rows = response.data if isinstance(response.data, list) else response.data['results']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['staff_name'], 'Asha')
        self.assertEqual(rows[0]['staff_role'], 'Tailor')
        self.assertIsNone(rows[0]['staff'])

    def test_a_former_colleagues_history_is_not_readable_by_staff(self):
        """Section 17: deletion must not widen anybody's view."""
        other_user = User.objects.create_user(
            username='bina', email='bina@retain.test', password='binapw12345')
        other = Tailor.objects.create(name='Bina', specialty='Lehengas',
                                      role='Tailor', user=other_user)
        StaffProfile.objects.create(staff=other)
        self.worked(1)
        self.staff.delete()

        response = self.client_for(other_user).get(reverse('staff-attendance-list'))
        self.assertEqual(response.status_code, 200)
        rows = response.data if isinstance(response.data, list) else response.data['results']
        self.assertNotIn('Asha', response.content.decode(),
                         "a colleague's history is not a colleague's business")

    def test_a_former_staff_token_gains_nothing_from_the_deletion(self):
        """Section 17, and the Phase 8 invariant, still holding."""
        api = self.client_for(self.staff_user)
        self.worked(1)
        self.client_for(self.owner).delete(
            reverse('tailor-detail', args=[self.staff.id]))
        for url in (reverse('staff-attendance-list'),
                    reverse('payroll-record-list'),
                    reverse('payroll-period-list')):
            self.assertIn(api.get(url).status_code, (401, 403), url)


class RetentionTenantIsolationTests(TransactionTestCase):
    """Section 16: deleting in one boutique must not touch the other."""

    def _boutique(self, schema, email, name):
        tenant = BoutiqueTenant(schema_name=schema, owner_email=email, name=name)
        tenant.save()
        Domain.objects.get_or_create(
            domain=f'{schema}.localhost', tenant=tenant,
            defaults={'is_primary': True})
        return tenant

    def setUp(self):
        connection.set_schema_to_public()
        self._boutique('retain_a', 'owner@ra.test', 'A')
        self._boutique('retain_b', 'owner@rb.test', 'B')
        self.ids = {}
        for schema, who in (('retain_a', 'A Worker'), ('retain_b', 'B Worker')):
            with schema_context(schema):
                staff = Tailor.objects.create(name=who, specialty='S', role='Tailor')
                StaffProfile.objects.create(staff=staff)
                session = AttendanceSession(
                    staff=staff, date=date(2026, 9, 1),
                    check_in=timezone.now())
                session.check_out = session.check_in + timedelta(hours=8)
                session.minutes = 480
                session.save()
                self.ids[schema] = (staff.id, session.id)
        connection.set_schema_to_public()

    def tearDown(self):
        connection.set_schema_to_public()
        for schema in ('retain_a', 'retain_b'):
            with connection.cursor() as c:
                c.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        BoutiqueTenant.objects.filter(
            schema_name__in=['retain_a', 'retain_b']).delete()

    def test_both_boutiques_share_a_staff_id(self):
        self.assertEqual(self.ids['retain_a'][0], self.ids['retain_b'][0])

    def test_deleting_in_one_boutique_leaves_the_other_untouched(self):
        with schema_context('retain_a'):
            Tailor.objects.get(id=self.ids['retain_a'][0]).delete()
            detached = AttendanceSession.objects.get()
            self.assertIsNone(detached.staff_id)
            self.assertEqual(detached.staff_name_snapshot, 'A Worker')

        with schema_context('retain_b'):
            intact = AttendanceSession.objects.get()
            self.assertIsNotNone(intact.staff_id, "B's history is not A's to touch")
            self.assertEqual(intact.staff_name_snapshot, 'B Worker')
            self.assertEqual(Tailor.objects.filter(name='B Worker').count(), 1)


class DepositAndPayoutHistoryTests(RetentionTestCase):
    """Sections 12 and 13: the whole money trail, after the person has gone."""

    def _paid_payroll(self):
        from apps.payroll import services
        self.worked(1)
        self.worked(2)
        period = services.generate(date(2026, 9, 1), user=self.owner)
        services.approve(period, user=self.owner)
        record = PayrollRecord.objects.get(staff=self.staff)
        payout = Payout.objects.create(
            payroll_record=record, staff=self.staff,
            staff_name_snapshot='Asha', amount=record.net_payable,
            method='CASH', paid_by=self.owner, paid_at=timezone.now())
        record.status = PayrollRecord.Status.PAID
        record.save(update_fields=['status'])
        return record, payout

    def test_a_payout_outlives_the_person_it_paid(self):
        record, payout = self._paid_payroll()
        amount = payout.amount
        self.staff.delete()
        payout.refresh_from_db()
        self.assertIsNone(payout.staff_id)
        self.assertEqual(payout.staff_name_snapshot, 'Asha')
        self.assertEqual(payout.amount, amount)
        self.assertIsNotNone(payout.payroll_record_id,
                             'the payout must still name what it settled')

    def test_the_deposit_ledger_outlives_the_person_it_recovered_from(self):
        self.profile.deposit_total = Decimal('5000.00')
        self.profile.deposit_weekly = Decimal('500.00')
        self.profile.save()
        entry = StaffLedgerEntry.objects.create(
            staff=self.staff, staff_name_snapshot='Asha',
            entry_type='DEPOSIT_AGREED', amount=Decimal('5000.00'),
            balance_before=Decimal('0.00'), balance_after=Decimal('5000.00'))
        self.staff.delete()
        entry.refresh_from_db()
        self.assertIsNone(entry.staff_id)
        self.assertEqual(entry.staff_name_snapshot, 'Asha')
        self.assertEqual(entry.balance_after, Decimal('5000.00'))

    def test_the_whole_chain_is_still_explainable(self):
        """Section 6: attendance -> record -> period -> payout, after deletion."""
        record, payout = self._paid_payroll()
        before = {
            'minutes': record.worked_minutes,
            'rate': record.hourly_rate_snapshot,
            'gross': record.gross_earnings,
            'net': record.net_payable,
            'period': record.period_id,
            'payout': payout.amount,
        }
        self.staff.delete()
        record.refresh_from_db()
        payout.refresh_from_db()
        self.assertEqual(record.worked_minutes, before['minutes'])
        self.assertEqual(record.hourly_rate_snapshot, before['rate'])
        self.assertEqual(record.gross_earnings, before['gross'])
        self.assertEqual(record.net_payable, before['net'])
        self.assertEqual(record.period_id, before['period'])
        self.assertEqual(payout.amount, before['payout'])
        self.assertEqual(record.staff_name_snapshot, 'Asha')
        # And the hours it was computed from.
        hours = AttendanceSession.objects.filter(staff_name_snapshot='Asha')
        self.assertEqual(sum(h.minutes for h in hours), before['minutes'])


class DeactivationTests(RetentionTestCase):
    """Section 11: deactivating is the softer path, and keeps everything."""

    def test_deactivating_the_login_keeps_the_roster_row_and_its_history(self):
        session = self.worked(1)
        self.staff_user.is_active = False
        self.staff_user.save(update_fields=['is_active'])

        session.refresh_from_db()
        self.assertIsNotNone(session.staff_id,
                             'deactivating a login is not removing the person')
        self.assertTrue(Tailor.objects.filter(pk=self.staff.pk).exists())

        api = self.client_for(self.staff_user)
        self.assertIn(api.get(reverse('staff-attendance-list')).status_code,
                      (401, 403), 'but the token must stop working')

    def test_the_owner_still_sees_a_deactivated_persons_history(self):
        self.worked(1)
        self.staff_user.is_active = False
        self.staff_user.save(update_fields=['is_active'])
        response = self.client_for(self.owner).get(reverse('staff-attendance-list'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Asha', response.content.decode())


class DeletionRaceTests(TransactionTestCase):
    """Section 25: deleting while money is being moved.

    The requirement is not that every interleaving succeeds -- it is that none
    of them produces an orphaned financial record, a duplicated recovery or a
    payroll computed against evidence that has gone.
    """

    def setUp(self):
        connection.set_schema_to_public()
        self.tenant = BoutiqueTenant(
            schema_name='retain_race', owner_email='owner@race9.test', name='Race')
        self.tenant.save()
        Domain.objects.get_or_create(
            domain='retain_race.localhost', tenant=self.tenant,
            defaults={'is_primary': True})
        with schema_context('retain_race'):
            self.owner = User.objects.create_user(
                username='owner@race9.test', email='owner@race9.test',
                password='ownerpw12345')
            self.staff = Tailor.objects.create(
                name='Racer', specialty='Stitching', role='Tailor')
            StaffProfile.objects.create(
                staff=self.staff, hourly_rate=Decimal('100.00'))
            check_in = timezone.datetime(2026, 9, 1, 9, 0, tzinfo=tenant_timezone())
            session = AttendanceSession(
                staff=self.staff, date=date(2026, 9, 1),
                check_in=check_in, check_out=check_in + timedelta(hours=8))
            session.minutes = 480
            session.save()
        connection.set_schema_to_public()

    def tearDown(self):
        connection.set_schema_to_public()
        with connection.cursor() as c:
            c.execute('DROP SCHEMA IF EXISTS "retain_race" CASCADE')
        BoutiqueTenant.objects.filter(schema_name='retain_race').delete()

    def test_deleting_between_generate_and_approve_leaves_no_orphan(self):
        from apps.payroll import services
        with schema_context('retain_race'):
            period = services.generate(date(2026, 9, 1), user=self.owner)
            record = PayrollRecord.objects.get(period=period)
            frozen = record.worked_minutes

            Tailor.objects.filter(pk=self.staff.pk).delete()

            record.refresh_from_db()
            self.assertIsNone(record.staff_id)
            self.assertEqual(record.staff_name_snapshot, 'Racer')
            self.assertEqual(record.worked_minutes, frozen,
                             'a frozen figure must not move when staff goes')
            # The evidence is still there, detached.
            self.assertEqual(
                AttendanceSession.objects.filter(staff__isnull=True).count(), 1)

    def test_approving_after_deletion_either_works_or_fails_cleanly(self):
        """Whatever it does, it must not invent or destroy money."""
        from apps.payroll import services
        with schema_context('retain_race'):
            period = services.generate(date(2026, 9, 1), user=self.owner)
            Tailor.objects.filter(pk=self.staff.pk).delete()
            try:
                services.approve(period, user=self.owner)
            except services.PayrollError:
                pass    # A deterministic refusal is an acceptable answer.
            record = PayrollRecord.objects.get(period=period)
            self.assertEqual(record.staff_name_snapshot, 'Racer')
            self.assertGreaterEqual(record.worked_minutes, 0)
            self.assertEqual(
                AttendanceSession.objects.filter(staff__isnull=True).count(), 1,
                'attendance must survive whichever way approval went')
