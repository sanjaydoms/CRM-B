"""Employment terms, and who may see them.

The test this file exists for is `test_a_tailor_cannot_read_a_colleagues_rate`.
Everything else here is ordinary CRUD cover; that one is the reason the model was
put in its own table instead of onto Tailor, and it is the assertion that will
fail if a later phase ever publishes these columns through the roster.
"""

from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

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
from core.formatting import tenant_timezone, to_local
from crm_api.models import Tailor
from tenants.models import BoutiqueTenant

from .attendance import business_date
from .models import AttendanceSession, StaffProfile
from .serializers import CONFIDENTIAL_FIELDS


class StaffProfileTestCase(TenantTestCase):
    """One boutique, an owner, and two staff members who are not each other."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = 'owner@staff.test'
        tenant.name = 'Staff Test Atelier'
        return tenant

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)

        # The owner is recognised by matching the tenant's owner_email -- the
        # positive check in core.roles, not by absence of a profile.
        self.owner = User.objects.create_user(
            username='owner@staff.test', email='owner@staff.test',
            password='ownerpass12345')

        self.anita_user = User.objects.create_user(
            username='anita', email='anita@staff.test', password='anitapass12345')
        self.anita = Tailor.objects.create(
            name='Anita', specialty='Blouses', role='Tailor',
            email='anita@staff.test', user=self.anita_user)

        self.balan_user = User.objects.create_user(
            username='balan', email='balan@staff.test', password='balanpass12345')
        self.balan = Tailor.objects.create(
            name='Balan', specialty='Lehengas', role='Tailor',
            email='balan@staff.test', user=self.balan_user)

    def client_for(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Token {token.key}',
                        HTTP_X_TENANT_ID=self.tenant.schema_name)
        return api

    def terms_for(self, tailor, **overrides):
        values = {
            'hourly_rate': Decimal('120.00'),
            'weekly_hours': Decimal('48.00'),
            'deposit_total': Decimal('5000.00'),
            'deposit_weekly': Decimal('500.00'),
            'joined_at': '2026-01-05',
        }
        values.update(overrides)
        return StaffProfile.objects.create(staff=tailor, **values)


class StaffProfileCrudTests(StaffProfileTestCase):
    def test_owner_creates_employment_terms(self):
        response = self.client_for(self.owner).post(
            reverse('staff-profile-list'),
            {'staff': self.anita.id, 'hourly_rate': '120.00',
             'deposit_total': '5000.00', 'deposit_weekly': '500.00',
             'employment_type': 'FULL_TIME', 'joined_at': '2026-01-05'},
            format='json')
        self.assertEqual(response.status_code, 201, response.data)
        profile = StaffProfile.objects.get(staff=self.anita)
        self.assertEqual(profile.hourly_rate, Decimal('120.00'))
        self.assertEqual(profile.deposit_weekly, Decimal('500.00'))

    def test_the_roster_row_travels_with_the_terms(self):
        self.terms_for(self.anita)
        response = self.client_for(self.owner).get(reverse('staff-profile-list'))
        self.assertEqual(response.status_code, 200)
        row = response.data[0]
        self.assertEqual(row['staff_name'], 'Anita')
        self.assertEqual(row['staff_role'], 'Tailor')

    def test_owner_edits_the_rate(self):
        profile = self.terms_for(self.anita)
        response = self.client_for(self.owner).patch(
            reverse('staff-profile-detail', args=[profile.id]),
            {'hourly_rate': '150.00'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        profile.refresh_from_db()
        self.assertEqual(profile.hourly_rate, Decimal('150.00'))

    def test_one_set_of_terms_per_staff_member(self):
        self.terms_for(self.anita)
        response = self.client_for(self.owner).post(
            reverse('staff-profile-list'),
            {'staff': self.anita.id, 'hourly_rate': '90.00'}, format='json')
        self.assertEqual(response.status_code, 400, response.data)

    def test_terms_cannot_be_moved_to_another_staff_member(self):
        """A PATCH naming a different person leaves the owner of the row alone.

        Honouring it would hand Balan Anita's rate and deposit and leave Anita
        with nothing, which no interface would ever ask for on purpose.
        """
        profile = self.terms_for(self.anita)
        response = self.client_for(self.owner).patch(
            reverse('staff-profile-detail', args=[profile.id]),
            {'staff': self.balan.id}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        profile.refresh_from_db()
        self.assertEqual(profile.staff_id, self.anita.id)

    def test_a_negative_rate_is_refused(self):
        response = self.client_for(self.owner).post(
            reverse('staff-profile-list'),
            {'staff': self.anita.id, 'hourly_rate': '-50.00'}, format='json')
        self.assertEqual(response.status_code, 400, response.data)

    def test_a_negative_deposit_is_refused(self):
        response = self.client_for(self.owner).post(
            reverse('staff-profile-list'),
            {'staff': self.anita.id, 'deposit_total': '-1.00'}, format='json')
        self.assertEqual(response.status_code, 400, response.data)

    def test_leaving_before_joining_is_refused(self):
        response = self.client_for(self.owner).post(
            reverse('staff-profile-list'),
            {'staff': self.anita.id, 'joined_at': '2026-06-01',
             'exit_date': '2026-01-01'}, format='json')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('exit_date', response.data)

    def test_leaving_before_joining_is_refused_across_two_requests(self):
        """The dates are compared with what is stored, not only with the body."""
        profile = self.terms_for(self.anita, joined_at='2026-06-01')
        response = self.client_for(self.owner).patch(
            reverse('staff-profile-detail', args=[profile.id]),
            {'exit_date': '2026-01-01'}, format='json')
        self.assertEqual(response.status_code, 400, response.data)

    def test_money_is_decimal_not_float(self):
        """0.10 + 0.20 has to be 0.30 in a table that will multiply by hours."""
        profile = self.terms_for(self.anita, hourly_rate=Decimal('0.10'))
        profile.refresh_from_db()
        self.assertIsInstance(profile.hourly_rate, Decimal)
        self.assertEqual(profile.hourly_rate + Decimal('0.20'), Decimal('0.30'))


class ExistingRosterIsUndisturbedTests(StaffProfileTestCase):
    """A boutique that never opens this screen must not notice it shipped."""

    def test_no_terms_are_conjured_for_anybody(self):
        """Nothing auto-creates employment records.

        A zero-rate profile invented for every existing tailor would enrol
        twenty people into a future payroll run nobody agreed to.
        """
        self.assertEqual(Tailor.objects.count(), 2)
        self.assertEqual(StaffProfile.objects.count(), 0)

    def test_a_tailor_without_terms_still_works(self):
        self.assertFalse(StaffProfile.objects.filter(staff=self.anita).exists())
        # The reverse accessor raises rather than returning None, which is what
        # any caller reading it must be ready for.
        with self.assertRaises(StaffProfile.DoesNotExist):
            _ = self.anita.staff_profile

    def test_the_roster_endpoint_still_lists_everyone(self):
        response = self.client_for(self.owner).get(reverse('tailor-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row['name'] for row in response.data}, {'Anita', 'Balan'})

    def test_the_roster_never_carries_employment_terms(self):
        """The whole reason StaffProfile is not columns on Tailor.

        TailorSerializer is fields='__all__', so a rate added to that model
        would appear here the day it was added. This asserts the separation
        holds -- it fails loudly if a later phase moves a money column onto the
        roster.
        """
        self.terms_for(self.anita)
        response = self.client_for(self.owner).get(reverse('tailor-list'))
        self.assertEqual(response.status_code, 200)
        for row in response.data:
            for confidential in ('hourly_rate', 'deposit_total', 'deposit_weekly',
                                 'weekly_hours', 'staff_profile'):
                self.assertNotIn(confidential, row)

    def test_deleting_a_staff_member_takes_their_terms_with_them(self):
        self.terms_for(self.anita)
        self.anita.delete()
        self.assertEqual(StaffProfile.objects.count(), 0)


class StaffProfileAuthorizationTests(StaffProfileTestCase):
    def test_signing_in_is_required(self):
        anonymous = APIClient()
        anonymous.credentials(HTTP_X_TENANT_ID=self.tenant.schema_name)
        response = anonymous.get(reverse('staff-profile-list'))
        self.assertIn(response.status_code, (401, 403))

    def test_owner_sees_the_whole_roster(self):
        self.terms_for(self.anita)
        self.terms_for(self.balan)
        response = self.client_for(self.owner).get(reverse('staff-profile-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)

    def test_a_tailor_sees_only_their_own_terms(self):
        self.terms_for(self.anita)
        self.terms_for(self.balan)
        response = self.client_for(self.anita_user).get(reverse('staff-profile-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['staff_name'], 'Anita')

    def test_a_tailor_cannot_read_a_colleagues_rate(self):
        """THE test this module exists for.

        Anita asks for Balan's employment record by id, which is the whole
        attack: the roster endpoint already tells her Balan's id. She must not
        get his rate, his deposit, or an acknowledgement that the row is there.
        """
        self.terms_for(self.anita)
        balan_terms = self.terms_for(
            self.balan, hourly_rate=Decimal('999.00'),
            deposit_total=Decimal('7000.00'), deposit_weekly=Decimal('700.00'))

        response = self.client_for(self.anita_user).get(
            reverse('staff-profile-detail', args=[balan_terms.id]))
        self.assertEqual(response.status_code, 404)

        body = response.content.decode()
        for leaked in ('999.00', '7000.00', '700.00'):
            self.assertNotIn(leaked, body)

        # And not through the list route either.
        listing = self.client_for(self.anita_user).get(reverse('staff-profile-list'))
        self.assertNotIn('999.00', listing.content.decode())

    def test_a_tailor_cannot_raise_their_own_pay(self):
        profile = self.terms_for(self.anita, hourly_rate=Decimal('120.00'))
        response = self.client_for(self.anita_user).patch(
            reverse('staff-profile-detail', args=[profile.id]),
            {'hourly_rate': '500.00'}, format='json')
        self.assertEqual(response.status_code, 403)
        profile.refresh_from_db()
        self.assertEqual(profile.hourly_rate, Decimal('120.00'))

    def test_a_tailor_cannot_create_employment_terms(self):
        response = self.client_for(self.anita_user).post(
            reverse('staff-profile-list'),
            {'staff': self.anita.id, 'hourly_rate': '500.00'}, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(StaffProfile.objects.count(), 0)

    def test_a_tailor_cannot_edit_a_colleagues_terms(self):
        balan_terms = self.terms_for(self.balan, hourly_rate=Decimal('120.00'))
        response = self.client_for(self.anita_user).patch(
            reverse('staff-profile-detail', args=[balan_terms.id]),
            {'hourly_rate': '1.00'}, format='json')
        self.assertIn(response.status_code, (403, 404))
        balan_terms.refresh_from_db()
        self.assertEqual(balan_terms.hourly_rate, Decimal('120.00'))

    def test_a_tailor_cannot_delete_terms(self):
        profile = self.terms_for(self.anita)
        response = self.client_for(self.anita_user).delete(
            reverse('staff-profile-detail', args=[profile.id]))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(StaffProfile.objects.count(), 1)

    def test_the_queryset_handles_an_account_with_no_roster_profile(self):
        """A login attached to no Tailor row must not raise.

        Pinned as a characterisation test, not an endorsement: such an account
        resolves to OWNER today, because core.roles falls through to OWNER when
        no profile claims a user. That is a PRE-EXISTING weakness its own
        docstring records and closes at the two sites where an account can be
        orphaned -- it is not introduced here and is not this phase's to fix.
        What this asserts is that the staff queryset copes with the case at all
        rather than throwing on a missing `tailor_profile`.
        """
        self.terms_for(self.anita)
        stranger = User.objects.create_user(
            username='stranger', email='stranger@staff.test', password='strangerpw123')
        response = self.client_for(stranger).get(reverse('staff-profile-list'))
        self.assertEqual(response.status_code, 200)


class StaffModuleGateTests(StaffProfileTestCase):
    def test_the_staff_module_is_gateable(self):
        from core.modules import module_for_path
        self.assertEqual(module_for_path('/api/staff/profiles/'), 'staff')

    def test_the_staff_module_is_on_for_a_boutique_that_has_no_opinion(self):
        """Absent means enabled -- or shipping this would switch it off for all."""
        from core.modules import default_enabled, is_enabled
        self.assertTrue(is_enabled({}, 'staff'))
        self.assertTrue(is_enabled({'inventory': False}, 'staff'))
        self.assertIs(default_enabled()['staff'], True)

    def test_gating_staff_does_not_gate_the_roster(self):
        from core.modules import module_for_path
        self.assertEqual(module_for_path('/api/tailors/'), 'tailors')


class StaffTenantIsolationTests(TenantTestCase):
    """Employment terms belong to one boutique and cannot be shared.

    Asserted structurally rather than by provisioning a second schema. What
    actually isolates this data is which app list the module is in: a table in
    TENANT_APPS is created once per boutique schema, so there is no shared table
    for another boutique's rows to be visible in. A migration that landed in
    SHARED_APPS would put every boutique's pay rates in one public table, and no
    amount of queryset filtering would undo that -- so this is the assertion
    worth pinning.
    """

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = 'owner@isolation.test'
        tenant.name = 'Isolation Atelier'
        return tenant

    def test_staff_lives_in_the_tenant_schema_not_the_public_one(self):
        from django.conf import settings
        self.assertIn('apps.staff', settings.TENANT_APPS)
        self.assertNotIn('apps.staff', settings.SHARED_APPS)

    def test_the_table_is_built_inside_a_boutique_schema(self):
        connection.set_tenant(self.tenant)
        tailor = Tailor.objects.create(name='Local', specialty='Sarees', role='Tailor')
        StaffProfile.objects.create(staff=tailor, hourly_rate=Decimal('100.00'))
        self.assertEqual(StaffProfile.objects.count(), 1)
        self.assertNotEqual(connection.schema_name, 'public')


class PermissionMatrixTests(StaffProfileTestCase):
    """Every existing role string, against every Staff Management endpoint.

    The matrix is written out per role rather than looped, because when one of
    these fails the useful thing is the name of the test, not an index into a
    table.
    """

    def setUp(self):
        super().setUp()
        # A supervisor and a specialist, so the matrix covers the real role
        # strings rather than just 'Tailor'.
        self.master_user = User.objects.create_user(
            username='mala', email='mala@staff.test', password='malapass12345')
        self.master = Tailor.objects.create(
            name='Mala', specialty='Supervision', role='Master',
            email='mala@staff.test', user=self.master_user)

        self.qc_user = User.objects.create_user(
            username='qadir', email='qadir@staff.test', password='qadirpass12345')
        self.qc = Tailor.objects.create(
            name='Qadir', specialty='Inspection', role='QC Master',
            email='qadir@staff.test', user=self.qc_user)

        self.anita_terms = self.terms_for(self.anita)
        self.balan_terms = self.terms_for(
            self.balan, hourly_rate=Decimal('999.00'),
            deposit_total=Decimal('7000.00'), deposit_weekly=Decimal('700.00'),
            weekly_hours=Decimal('44.00'))
        self.master_terms = self.terms_for(self.master, hourly_rate=Decimal('300.00'))

    # ---- Owner -----------------------------------------------------------
    def test_owner_lists_every_profile(self):
        response = self.client_for(self.owner).get(reverse('staff-profile-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 3)

    def test_owner_reads_every_confidential_field(self):
        response = self.client_for(self.owner).get(
            reverse('staff-profile-detail', args=[self.balan_terms.id]))
        self.assertEqual(response.status_code, 200)
        for field in CONFIDENTIAL_FIELDS:
            self.assertIn(field, response.data)
        self.assertEqual(response.data['hourly_rate'], '999.00')

    def test_owner_creates_and_edits(self):
        newcomer = Tailor.objects.create(
            name='Nadia', specialty='Finishing', role='Finishing Master')
        created = self.client_for(self.owner).post(
            reverse('staff-profile-list'),
            {'staff': newcomer.id, 'hourly_rate': '111.00'}, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        edited = self.client_for(self.owner).patch(
            reverse('staff-profile-detail', args=[created.data['id']]),
            {'hourly_rate': '112.00'}, format='json')
        self.assertEqual(edited.status_code, 200, edited.data)

    # ---- Master (supervisor) ---------------------------------------------
    def test_master_lists_the_team(self):
        response = self.client_for(self.master_user).get(reverse('staff-profile-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 3)

    def test_master_cannot_read_the_teams_pay(self):
        """A supervisor sees who is on the floor, not what the floor is paid."""
        response = self.client_for(self.master_user).get(
            reverse('staff-profile-detail', args=[self.balan_terms.id]))
        self.assertEqual(response.status_code, 200)
        for field in CONFIDENTIAL_FIELDS:
            self.assertNotIn(field, response.data)
        self.assertNotIn('999.00', response.content.decode())
        # What supervision legitimately needs is still there.
        self.assertEqual(response.data['staff_name'], 'Balan')
        self.assertIn('joined_at', response.data)

    def test_master_reads_their_own_pay(self):
        response = self.client_for(self.master_user).get(
            reverse('staff-profile-detail', args=[self.master_terms.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['hourly_rate'], '300.00')

    def test_the_master_listing_carries_no_colleague_pay(self):
        body = self.client_for(self.master_user).get(
            reverse('staff-profile-list')).content.decode()
        self.assertNotIn('999.00', body)
        self.assertNotIn('7000.00', body)
        # Their own rate survives the same response.
        self.assertIn('300.00', body)

    def test_master_cannot_create_a_profile(self):
        newcomer = Tailor.objects.create(
            name='Omar', specialty='Pressing', role='Pressing Staff')
        response = self.client_for(self.master_user).post(
            reverse('staff-profile-list'),
            {'staff': newcomer.id, 'hourly_rate': '100.00'}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_master_cannot_change_a_rate(self):
        response = self.client_for(self.master_user).patch(
            reverse('staff-profile-detail', args=[self.balan_terms.id]),
            {'hourly_rate': '1.00'}, format='json')
        self.assertEqual(response.status_code, 403)
        self.balan_terms.refresh_from_db()
        self.assertEqual(self.balan_terms.hourly_rate, Decimal('999.00'))

    def test_master_cannot_change_deposit_terms(self):
        response = self.client_for(self.master_user).patch(
            reverse('staff-profile-detail', args=[self.balan_terms.id]),
            {'deposit_weekly': '5000.00'}, format='json')
        self.assertEqual(response.status_code, 403)
        self.balan_terms.refresh_from_db()
        self.assertEqual(self.balan_terms.deposit_weekly, Decimal('700.00'))

    def test_master_cannot_raise_their_own_pay(self):
        response = self.client_for(self.master_user).patch(
            reverse('staff-profile-detail', args=[self.master_terms.id]),
            {'hourly_rate': '9000.00'}, format='json')
        self.assertEqual(response.status_code, 403)
        self.master_terms.refresh_from_db()
        self.assertEqual(self.master_terms.hourly_rate, Decimal('300.00'))

    def test_master_cannot_delete(self):
        response = self.client_for(self.master_user).delete(
            reverse('staff-profile-detail', args=[self.balan_terms.id]))
        self.assertEqual(response.status_code, 403)

    # ---- Tailor ----------------------------------------------------------
    def test_tailor_sees_only_themselves(self):
        response = self.client_for(self.anita_user).get(reverse('staff-profile-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['staff_name'], 'Anita')

    def test_tailor_reads_their_own_terms_in_full(self):
        response = self.client_for(self.anita_user).get(
            reverse('staff-profile-detail', args=[self.anita_terms.id]))
        self.assertEqual(response.status_code, 200)
        for field in CONFIDENTIAL_FIELDS:
            self.assertIn(field, response.data)

    def test_tailor_gets_a_scoped_404_for_a_colleague(self):
        response = self.client_for(self.anita_user).get(
            reverse('staff-profile-detail', args=[self.balan_terms.id]))
        self.assertEqual(response.status_code, 404)

    # ---- Specialist ------------------------------------------------------
    def test_specialist_is_not_a_supervisor(self):
        """A QC Master is a specialist, not a Master. The names are close."""
        response = self.client_for(self.qc_user).get(reverse('staff-profile-list'))
        self.assertEqual(response.status_code, 200)
        # No profile of their own, and no right to anyone else's.
        self.assertEqual(len(response.data), 0)

    def test_specialist_with_terms_sees_only_their_own(self):
        qc_terms = self.terms_for(self.qc, hourly_rate=Decimal('210.00'))
        response = self.client_for(self.qc_user).get(reverse('staff-profile-list'))
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], str(qc_terms.id))
        self.assertNotIn('999.00', response.content.decode())

    def test_specialist_cannot_write(self):
        qc_terms = self.terms_for(self.qc)
        response = self.client_for(self.qc_user).patch(
            reverse('staff-profile-detail', args=[qc_terms.id]),
            {'hourly_rate': '900.00'}, format='json')
        self.assertEqual(response.status_code, 403)

    # ---- Designer --------------------------------------------------------
    def test_a_design_only_account_gets_no_staff_records(self):
        """Designers have no Tailor row, so they match no employment record.

        Left as an empty list rather than a refusal: the endpoint is not theirs
        to be refused from, and returning nothing is the same answer the
        queryset gives any account with no roster profile.
        """
        from apps.design_studio.models import Designer
        designer_user = User.objects.create_user(
            username='dia', email='dia@staff.test', password='diapass12345')
        Designer.objects.create(name='Dia', email='dia@staff.test', user=designer_user)

        response = self.client_for(designer_user).get(reverse('staff-profile-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 0)
        self.assertNotIn('999.00', response.content.decode())

    def test_a_designer_cannot_write_employment_terms(self):
        from apps.design_studio.models import Designer
        designer_user = User.objects.create_user(
            username='dev', email='dev@staff.test', password='devpass12345')
        Designer.objects.create(name='Dev', email='dev@staff.test', user=designer_user)
        response = self.client_for(designer_user).patch(
            reverse('staff-profile-detail', args=[self.balan_terms.id]),
            {'hourly_rate': '1.00'}, format='json')
        self.assertIn(response.status_code, (403, 404))
        self.balan_terms.refresh_from_db()
        self.assertEqual(self.balan_terms.hourly_rate, Decimal('999.00'))

    # ---- Customer / anonymous -------------------------------------------
    def test_a_customer_has_no_account_and_no_access(self):
        anonymous = APIClient()
        anonymous.credentials(HTTP_X_TENANT_ID=self.tenant.schema_name)
        for url in (reverse('staff-profile-list'),
                    reverse('staff-profile-detail', args=[self.balan_terms.id])):
            response = anonymous.get(url)
            self.assertIn(response.status_code, (401, 403))


class CrossTenantStaffTests(TransactionTestCase):
    """Two real boutiques, two real schemas, and no way across.

    Not a TenantTestCase: that builds ONE tenant, and one tenant cannot show
    that a second is unreachable. This provisions two the way signup does, so
    the isolation under test is the isolation production actually has --
    django-tenants switching `search_path` per request from the X-Tenant-ID
    header.

    Expensive, and deliberately the only test here that is. Cross-tenant leakage
    is the failure that would end a multi-boutique product, and it is not a
    thing to infer from a frozenset.
    """

    def setUp(self):
        connection.set_schema_to_public()
        self.alpha = self._boutique('xt_alpha', 'owner@alpha.test', 'Alpha Atelier')
        self.beta = self._boutique('xt_beta', 'owner@beta.test', 'Beta Boutique')

        self.alpha_staff, self.alpha_terms = self._staff(
            self.alpha, 'alphatailor@alpha.test', 'Alpha Tailor',
            Decimal('111.11'), Decimal('1100.00'))
        self.beta_staff, self.beta_terms = self._staff(
            self.beta, 'betatailor@beta.test', 'Beta Tailor',
            Decimal('222.22'), Decimal('2200.00'))
        connection.set_schema_to_public()

    def tearDown(self):
        connection.set_schema_to_public()
        for schema in ('xt_alpha', 'xt_beta'):
            with connection.cursor() as c:
                c.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            BoutiqueTenant.objects.filter(schema_name=schema).delete()

    @staticmethod
    def _boutique(schema, owner_email, name):
        tenant = BoutiqueTenant(schema_name=schema, owner_email=owner_email, name=name)
        tenant.save()  # auto_create_schema runs every tenant migration
        return tenant

    @staticmethod
    def _staff(tenant, email, name, rate, deposit):
        with schema_context(tenant.schema_name):
            user = User.objects.create_user(
                username=email, email=email, password='crosstenantpw12345')
            tailor = Tailor.objects.create(
                name=name, specialty='Stitching', role='Tailor',
                email=email, user=user)
            terms = StaffProfile.objects.create(
                staff=tailor, hourly_rate=rate, deposit_total=deposit)
            Token.objects.get_or_create(user=user)
        return tailor, terms

    def _client(self, tenant, email):
        with schema_context(tenant.schema_name):
            token = Token.objects.get(user__email=email).key
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Token {token}',
                        HTTP_X_TENANT_ID=tenant.schema_name)
        return api

    def test_each_boutique_sees_only_its_own_staff(self):
        alpha = self._client(self.alpha, 'alphatailor@alpha.test')
        response = alpha.get(reverse('staff-profile-list'))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('111.11', body)
        self.assertNotIn('222.22', body)
        self.assertNotIn('Beta Tailor', body)

    def test_a_token_from_one_boutique_is_not_a_token_in_another(self):
        """Alpha's staff, pointed at Beta's schema, is simply not a user there.

        The token table lives in each tenant schema, so the row backing this
        credential does not exist in Beta -- authentication fails before any
        staff code runs. That is the isolation, and it is the database's rather
        than a filter anyone could forget to write.
        """
        with schema_context(self.alpha.schema_name):
            stolen = Token.objects.get(user__email='alphatailor@alpha.test').key
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Token {stolen}',
                        HTTP_X_TENANT_ID=self.beta.schema_name)
        response = api.get(reverse('staff-profile-list'))
        self.assertIn(response.status_code, (401, 403))
        self.assertNotIn('222.22', response.content.decode())

    def test_a_profile_id_from_another_boutique_is_not_found(self):
        """Beta's row id, asked for with Alpha's credentials, must 404."""
        alpha = self._client(self.alpha, 'alphatailor@alpha.test')
        response = alpha.get(
            reverse('staff-profile-detail', args=[self.beta_terms.id]))
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('222.22', response.content.decode())

    def test_an_owner_cannot_reach_the_other_boutiques_staff(self):
        """Being an owner is a role inside one schema, not across the platform."""
        with schema_context(self.alpha.schema_name):
            owner = User.objects.create_user(
                username='owner@alpha.test', email='owner@alpha.test',
                password='alphaownerpw12345')
            token = Token.objects.create(user=owner).key
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Token {token}',
                        HTTP_X_TENANT_ID=self.alpha.schema_name)
        response = api.get(reverse('staff-profile-list'))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('111.11', body)
        self.assertNotIn('222.22', body)
        self.assertNotIn('Beta Tailor', body)


class AttendanceTestCase(StaffProfileTestCase):
    """Attendance rides on the same boutique, owner and two tailors."""

    def setUp(self):
        super().setUp()
        self.master_user = User.objects.create_user(
            username='mira', email='mira@staff.test', password='mirapass12345')
        self.master = Tailor.objects.create(
            name='Mira', specialty='Supervision', role='Master',
            email='mira@staff.test', user=self.master_user)

    @staticmethod
    def _at(year, month, day, hour, minute):
        """An aware instant in the boutique's own timezone."""
        return datetime(year, month, day, hour, minute,
                        tzinfo=tenant_timezone())


class CheckInTests(AttendanceTestCase):
    def test_a_tailor_checks_themselves_in(self):
        response = self.client_for(self.anita_user).post(
            reverse('staff-attendance-check-in'), {}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        session = AttendanceSession.objects.get()
        self.assertEqual(session.staff, self.anita)
        self.assertEqual(session.source, 'SELF')
        self.assertIsNone(session.check_out)
        self.assertIsNone(session.minutes)

    def test_the_server_stamps_the_time_not_the_client(self):
        """A check-in time sent by the client is ignored outright."""
        before = timezone.now()
        response = self.client_for(self.anita_user).post(
            reverse('staff-attendance-check-in'),
            {'check_in': '2001-01-01T04:00:00Z'}, format='json')
        self.assertEqual(response.status_code, 201)
        session = AttendanceSession.objects.get()
        self.assertGreaterEqual(session.check_in, before)
        self.assertNotEqual(session.check_in.year, 2001)

    def test_a_second_check_in_is_refused_while_one_is_open(self):
        client = self.client_for(self.anita_user)
        self.assertEqual(client.post(reverse('staff-attendance-check-in'),
                                     {}, format='json').status_code, 201)
        second = client.post(reverse('staff-attendance-check-in'), {}, format='json')
        self.assertEqual(second.status_code, 400)
        self.assertIn('already checked in', second.data['error'])
        self.assertEqual(AttendanceSession.objects.count(), 1)

    def test_the_database_refuses_two_open_sessions(self):
        """The partial unique index, not just the view's pre-check.

        This is what holds when two taps race past the read.
        """
        AttendanceSession.objects.create(
            staff=self.anita, date=date(2026, 9, 1),
            check_in=self._at(2026, 9, 1, 9, 0))
        with self.assertRaises(IntegrityError):
            AttendanceSession.objects.create(
                staff=self.anita, date=date(2026, 9, 1),
                check_in=self._at(2026, 9, 1, 10, 0))

    def test_two_staff_may_both_be_checked_in(self):
        """The constraint is per person, not per boutique."""
        self.assertEqual(self.client_for(self.anita_user).post(
            reverse('staff-attendance-check-in'), {}, format='json').status_code, 201)
        self.assertEqual(self.client_for(self.balan_user).post(
            reverse('staff-attendance-check-in'), {}, format='json').status_code, 201)
        self.assertEqual(AttendanceSession.objects.count(), 2)

    def test_an_account_off_the_roster_cannot_check_in(self):
        stranger = User.objects.create_user(
            username='ghost', email='ghost@staff.test', password='ghostpass12345')
        response = self.client_for(stranger).post(
            reverse('staff-attendance-check-in'), {}, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(AttendanceSession.objects.count(), 0)

    def test_checking_in_requires_signing_in(self):
        anonymous = APIClient()
        anonymous.credentials(HTTP_X_TENANT_ID=self.tenant.schema_name)
        response = anonymous.post(reverse('staff-attendance-check-in'), {}, format='json')
        self.assertIn(response.status_code, (401, 403))

    def test_checking_in_writes_an_activity_row(self):
        self.client_for(self.anita_user).post(
            reverse('staff-attendance-check-in'), {}, format='json')
        entry = UniversalActivity.objects.get(module='staff')
        self.assertEqual(entry.action, 'CHECKED_IN')
        self.assertIn('Anita', entry.title)


class CheckOutTests(AttendanceTestCase):
    def test_a_tailor_checks_themselves_out(self):
        client = self.client_for(self.anita_user)
        client.post(reverse('staff-attendance-check-in'), {}, format='json')
        response = client.post(reverse('staff-attendance-check-out'), {}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        session = AttendanceSession.objects.get()
        self.assertIsNotNone(session.check_out)
        self.assertIsNotNone(session.minutes)
        self.assertGreaterEqual(session.minutes, 0)

    def test_checking_out_with_no_open_session_is_refused(self):
        response = self.client_for(self.anita_user).post(
            reverse('staff-attendance-check-out'), {}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('not checked in', response.data['error'])

    def test_checking_out_twice_is_refused(self):
        client = self.client_for(self.anita_user)
        client.post(reverse('staff-attendance-check-in'), {}, format='json')
        self.assertEqual(client.post(reverse('staff-attendance-check-out'),
                                     {}, format='json').status_code, 200)
        second = client.post(reverse('staff-attendance-check-out'), {}, format='json')
        self.assertEqual(second.status_code, 400)

    def test_the_duration_is_the_gap_between_the_stamps(self):
        session = AttendanceSession.objects.create(
            staff=self.anita, date=date(2026, 9, 1),
            check_in=self._at(2026, 9, 1, 9, 5),
            check_out=self._at(2026, 9, 1, 18, 30))
        self.assertEqual(session.duration_minutes(), 565)

    def test_an_overnight_shift_spans_midnight(self):
        """23:00 to 07:00 is eight hours, not a negative number or a rejection."""
        session = AttendanceSession.objects.create(
            staff=self.anita, date=date(2026, 9, 1),
            check_in=self._at(2026, 9, 1, 23, 0),
            check_out=self._at(2026, 9, 2, 7, 0))
        session.minutes = session.duration_minutes()
        self.assertEqual(session.minutes, 480)
        # It belongs to the night it STARTED on.
        self.assertEqual(session.date, date(2026, 9, 1))

    def test_an_open_session_has_no_duration_yet(self):
        session = AttendanceSession.objects.create(
            staff=self.anita, date=date(2026, 9, 1),
            check_in=self._at(2026, 9, 1, 9, 0))
        self.assertIsNone(session.duration_minutes())
        self.assertTrue(session.is_open)

    def test_the_database_refuses_a_shift_that_ends_before_it_starts(self):
        with self.assertRaises(IntegrityError):
            AttendanceSession.objects.create(
                staff=self.anita, date=date(2026, 9, 1),
                check_in=self._at(2026, 9, 1, 18, 0),
                check_out=self._at(2026, 9, 1, 9, 0))


class BusinessDateTests(AttendanceTestCase):
    def test_the_shift_is_filed_under_the_boutiques_own_date(self):
        """A morning start in Kolkata must not land on yesterday.

        05:30 in Asia/Kolkata is 00:00 UTC the same day; 00:30 local is 19:00
        UTC the day BEFORE. Filing by the UTC date would move that shift to the
        wrong day of the timesheet, and the week it is paid in.
        """
        self.tenant.timezone = 'Asia/Kolkata'
        self.tenant.save()
        local_midnight_thirty = datetime(
            2026, 9, 2, 0, 30, tzinfo=ZoneInfo('Asia/Kolkata'))
        self.assertEqual(local_midnight_thirty.astimezone(dt_timezone.utc).date(),
                         date(2026, 9, 1))
        self.assertEqual(business_date(local_midnight_thirty), date(2026, 9, 2))


class OwnerRecordedAttendanceTests(AttendanceTestCase):
    def test_owner_records_a_missed_day(self):
        response = self.client_for(self.owner).post(
            reverse('staff-attendance-record'),
            {'staff': self.anita.id,
             'check_in': '2026-09-01T09:10:00',
             'check_out': '2026-09-01T18:20:00',
             'note': 'Forgot to check in'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        session = AttendanceSession.objects.get()
        self.assertEqual(session.source, 'OWNER')
        self.assertEqual(session.minutes, 550)

    def test_an_owner_entry_is_distinguishable_from_a_self_check_in(self):
        self.client_for(self.owner).post(
            reverse('staff-attendance-record'),
            {'staff': self.anita.id, 'check_in': '2026-09-01T09:00:00',
             'check_out': '2026-09-01T17:00:00'}, format='json')
        self.client_for(self.balan_user).post(
            reverse('staff-attendance-check-in'), {}, format='json')
        self.assertEqual(
            AttendanceSession.objects.get(staff=self.anita).source, 'OWNER')
        self.assertEqual(
            AttendanceSession.objects.get(staff=self.balan).source, 'SELF')

    def test_a_naive_time_is_read_in_the_boutiques_timezone(self):
        """09:10 typed by an Indian boutique is 09:10 there, not 09:10 UTC."""
        self.tenant.timezone = 'Asia/Kolkata'
        self.tenant.save()
        self.client_for(self.owner).post(
            reverse('staff-attendance-record'),
            {'staff': self.anita.id, 'check_in': '2026-09-01T09:10:00',
             'check_out': '2026-09-01T18:20:00'}, format='json')
        session = AttendanceSession.objects.get()
        self.assertEqual(to_local(session.check_in).hour, 9)
        self.assertEqual(to_local(session.check_in).minute, 10)
        self.assertEqual(session.date, date(2026, 9, 1))

    def test_a_tailor_cannot_record_attendance_for_anyone(self):
        response = self.client_for(self.anita_user).post(
            reverse('staff-attendance-record'),
            {'staff': self.balan.id, 'check_in': '2026-09-01T09:00:00'},
            format='json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(AttendanceSession.objects.count(), 0)

    def test_a_master_cannot_record_attendance(self):
        response = self.client_for(self.master_user).post(
            reverse('staff-attendance-record'),
            {'staff': self.anita.id, 'check_in': '2026-09-01T09:00:00'},
            format='json')
        self.assertEqual(response.status_code, 403)

    def test_a_checkout_before_the_check_in_is_refused(self):
        response = self.client_for(self.owner).post(
            reverse('staff-attendance-record'),
            {'staff': self.anita.id, 'check_in': '2026-09-01T18:00:00',
             'check_out': '2026-09-01T09:00:00'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('before', response.data['error'])

    def test_an_unparseable_time_is_refused(self):
        response = self.client_for(self.owner).post(
            reverse('staff-attendance-record'),
            {'staff': self.anita.id, 'check_in': 'yesterday morning'},
            format='json')
        self.assertEqual(response.status_code, 400)

    def test_recording_for_an_unknown_staff_member_is_a_404(self):
        response = self.client_for(self.owner).post(
            reverse('staff-attendance-record'),
            {'staff': 999999, 'check_in': '2026-09-01T09:00:00'}, format='json')
        self.assertEqual(response.status_code, 404)


class AttendanceCorrectionTests(AttendanceTestCase):
    def setUp(self):
        super().setUp()
        self.session = AttendanceSession.objects.create(
            staff=self.anita, date=date(2026, 9, 1),
            check_in=self._at(2026, 9, 1, 9, 45),
            check_out=self._at(2026, 9, 1, 18, 0),
            minutes=495)

    def _correct(self, client, **payload):
        return client.post(
            reverse('staff-attendance-correct', args=[self.session.id]),
            payload, format='json')

    def test_owner_corrects_a_check_in_and_the_original_survives(self):
        response = self._correct(
            self.client_for(self.owner),
            check_in='2026-09-01T09:05:00', reason='Forgot to check in')
        self.assertEqual(response.status_code, 200, response.data)
        self.session.refresh_from_db()
        self.assertEqual(to_local(self.session.check_in).hour, 9)
        self.assertEqual(to_local(self.session.check_in).minute, 5)
        # What it used to say is still on the row.
        self.assertEqual(to_local(self.session.original_check_in).minute, 45)
        self.assertEqual(self.session.correction_reason, 'Forgot to check in')
        self.assertEqual(self.session.corrected_by, self.owner)
        self.assertIsNotNone(self.session.corrected_at)

    def test_the_duration_is_recalculated(self):
        self._correct(self.client_for(self.owner),
                      check_in='2026-09-01T09:05:00', reason='Forgot to check in')
        self.session.refresh_from_db()
        self.assertEqual(self.session.minutes, 535)

    def test_a_reason_is_required(self):
        response = self._correct(self.client_for(self.owner),
                                 check_in='2026-09-01T09:05:00')
        self.assertEqual(response.status_code, 400)
        self.assertIn('reason', response.data['error'].lower())
        self.session.refresh_from_db()
        self.assertEqual(to_local(self.session.check_in).minute, 45)

    def test_a_blank_reason_is_refused(self):
        response = self._correct(self.client_for(self.owner),
                                 check_in='2026-09-01T09:05:00', reason='   ')
        self.assertEqual(response.status_code, 400)

    def test_the_first_original_survives_a_second_correction(self):
        owner = self.client_for(self.owner)
        self._correct(owner, check_in='2026-09-01T09:05:00', reason='First fix')
        self._correct(owner, check_in='2026-09-01T09:00:00', reason='Second fix')
        self.session.refresh_from_db()
        # Still the value it had before ANY correction.
        self.assertEqual(to_local(self.session.original_check_in).minute, 45)
        self.assertEqual(self.session.correction_reason, 'Second fix')

    def test_every_correction_is_on_the_activity_feed(self):
        owner = self.client_for(self.owner)
        self._correct(owner, check_in='2026-09-01T09:05:00', reason='First fix')
        self._correct(owner, check_in='2026-09-01T09:00:00', reason='Second fix')
        entries = UniversalActivity.objects.filter(
            module='staff', action='ATTENDANCE_CORRECTED').order_by('timestamp')
        self.assertEqual(entries.count(), 2)
        self.assertIn('reason', entries[0].new_value)
        self.assertIn('check_in', entries[0].old_value)

    def test_a_correction_that_inverts_the_shift_is_refused(self):
        response = self._correct(self.client_for(self.owner),
                                 check_in='2026-09-01T20:00:00', reason='Typo')
        self.assertEqual(response.status_code, 400)

    def test_a_tailor_cannot_correct_their_own_attendance(self):
        response = self._correct(self.client_for(self.anita_user),
                                 check_in='2026-09-01T06:00:00', reason='More hours')
        self.assertEqual(response.status_code, 403)
        self.session.refresh_from_db()
        self.assertEqual(to_local(self.session.check_in).minute, 45)

    def test_a_master_cannot_correct_attendance(self):
        """Supervisors watch the floor; they do not edit what becomes wages."""
        response = self._correct(self.client_for(self.master_user),
                                 check_in='2026-09-01T06:00:00', reason='Adjust')
        self.assertEqual(response.status_code, 403)
        self.session.refresh_from_db()
        self.assertEqual(self.session.minutes, 495)


class AttendanceVisibilityTests(AttendanceTestCase):
    def setUp(self):
        super().setUp()
        self.anita_session = AttendanceSession.objects.create(
            staff=self.anita, date=date(2026, 9, 1),
            check_in=self._at(2026, 9, 1, 9, 0),
            check_out=self._at(2026, 9, 1, 17, 0), minutes=480)
        self.balan_session = AttendanceSession.objects.create(
            staff=self.balan, date=date(2026, 9, 1),
            check_in=self._at(2026, 9, 1, 10, 0),
            check_out=self._at(2026, 9, 1, 19, 0), minutes=540)

    def test_owner_sees_the_whole_floor(self):
        response = self.client_for(self.owner).get(reverse('staff-attendance-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)

    def test_a_master_sees_the_team(self):
        response = self.client_for(self.master_user).get(reverse('staff-attendance-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)

    def test_a_tailor_sees_only_their_own_days(self):
        response = self.client_for(self.anita_user).get(reverse('staff-attendance-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['staff_name'], 'Anita')

    def test_a_tailor_cannot_ask_for_a_colleague_by_query_parameter(self):
        """?staff= is simply not read on the staff branch."""
        response = self.client_for(self.anita_user).get(
            reverse('staff-attendance-list'), {'staff': self.balan.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['staff_name'], 'Anita')

    def test_a_tailor_cannot_fetch_a_colleagues_session_by_id(self):
        response = self.client_for(self.anita_user).get(
            reverse('staff-attendance-detail', args=[self.balan_session.id]))
        self.assertEqual(response.status_code, 404)

    def test_the_owner_can_filter_to_one_person(self):
        response = self.client_for(self.owner).get(
            reverse('staff-attendance-list'), {'staff': self.balan.id})
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['staff_name'], 'Balan')

    def test_attendance_cannot_be_written_through_the_router(self):
        """No generic create: every write is a named action with its own rules."""
        response = self.client_for(self.owner).post(
            reverse('staff-attendance-list'),
            {'staff': self.anita.id, 'check_in': '2026-09-01T09:00:00'},
            format='json')
        self.assertEqual(response.status_code, 405)


class CurrentAttendanceStateTests(AttendanceTestCase):
    def test_not_checked_in(self):
        response = self.client_for(self.anita_user).get(
            reverse('staff-attendance-current'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['state'], 'NOT_CHECKED_IN')
        self.assertIsNone(response.data['session'])

    def test_currently_working(self):
        client = self.client_for(self.anita_user)
        client.post(reverse('staff-attendance-check-in'), {}, format='json')
        response = client.get(reverse('staff-attendance-current'))
        self.assertEqual(response.data['state'], 'WORKING')
        self.assertTrue(response.data['session']['is_open'])

    def test_checked_out(self):
        client = self.client_for(self.anita_user)
        client.post(reverse('staff-attendance-check-in'), {}, format='json')
        client.post(reverse('staff-attendance-check-out'), {}, format='json')
        response = client.get(reverse('staff-attendance-current'))
        self.assertEqual(response.data['state'], 'CHECKED_OUT')
        self.assertFalse(response.data['session']['is_open'])

    def test_an_account_off_the_roster_gets_a_plain_answer(self):
        stranger = User.objects.create_user(
            username='nobody', email='nobody@staff.test', password='nobodypw12345')
        response = self.client_for(stranger).get(reverse('staff-attendance-current'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['state'], 'NOT_STAFF')


class TimesheetTests(AttendanceTestCase):
    def setUp(self):
        super().setUp()
        # Monday 31 Aug 2026 through Wednesday 2 Sep.
        for day, start, end in ((31, 9, 18), (1, 9, 17), (2, 10, 19)):
            month = 8 if day == 31 else 9
            session = AttendanceSession.objects.create(
                staff=self.anita, date=date(2026, month, day),
                check_in=self._at(2026, month, day, start, 0),
                check_out=self._at(2026, month, day, end, 0))
            session.minutes = session.duration_minutes()
            session.save()

    def test_a_week_totals_its_sessions(self):
        response = self.client_for(self.owner).get(
            reverse('staff-timesheet'), {'staff': self.anita.id, 'week': '2026-09-01'})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['week_start'], date(2026, 8, 31))
        self.assertEqual(response.data['week_end'], date(2026, 9, 6))
        self.assertEqual(len(response.data['sessions']), 3)
        # 9h + 8h + 9h
        self.assertEqual(response.data['total_minutes'], 540 + 480 + 540)

    def test_an_empty_week_totals_zero(self):
        response = self.client_for(self.owner).get(
            reverse('staff-timesheet'), {'staff': self.anita.id, 'week': '2026-10-05'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total_minutes'], 0)
        self.assertEqual(response.data['sessions'], [])

    def test_two_sessions_in_one_day_both_count(self):
        extra = AttendanceSession.objects.create(
            staff=self.anita, date=date(2026, 9, 3),
            check_in=self._at(2026, 9, 3, 9, 0),
            check_out=self._at(2026, 9, 3, 12, 0))
        extra.minutes = extra.duration_minutes()
        extra.save()
        second = AttendanceSession.objects.create(
            staff=self.anita, date=date(2026, 9, 3),
            check_in=self._at(2026, 9, 3, 14, 0),
            check_out=self._at(2026, 9, 3, 18, 0))
        second.minutes = second.duration_minutes()
        second.save()
        response = self.client_for(self.owner).get(
            reverse('staff-timesheet'), {'staff': self.anita.id, 'week': '2026-09-01'})
        self.assertEqual(len(response.data['sessions']), 5)
        self.assertEqual(response.data['total_minutes'], 1560 + 180 + 240)

    def test_an_open_session_contributes_no_minutes(self):
        """Otherwise the weekly total would change on every page refresh."""
        AttendanceSession.objects.create(
            staff=self.anita, date=date(2026, 9, 4),
            check_in=self._at(2026, 9, 4, 9, 0))
        response = self.client_for(self.owner).get(
            reverse('staff-timesheet'), {'staff': self.anita.id, 'week': '2026-09-01'})
        self.assertEqual(response.data['total_minutes'], 1560)
        self.assertEqual(response.data['open_sessions'], 1)

    def test_a_tailor_sees_their_own_timesheet_without_naming_themselves(self):
        response = self.client_for(self.anita_user).get(reverse('staff-timesheet'),
                                                        {'week': '2026-09-01'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['staff_name'], 'Anita')
        self.assertEqual(response.data['total_minutes'], 1560)

    def test_a_tailor_cannot_request_a_colleagues_timesheet(self):
        """THE query-parameter attack: ?staff=<someone else>.

        The parameter is ignored rather than refused, so the answer is the
        caller's own week and nothing leaks about whether that id exists.
        """
        AttendanceSession.objects.create(
            staff=self.balan, date=date(2026, 9, 1),
            check_in=self._at(2026, 9, 1, 8, 0),
            check_out=self._at(2026, 9, 1, 20, 0), minutes=720)
        response = self.client_for(self.anita_user).get(
            reverse('staff-timesheet'), {'staff': self.balan.id, 'week': '2026-09-01'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['staff_name'], 'Anita')
        self.assertNotEqual(response.data['total_minutes'], 720)

    def test_a_master_may_read_the_teams_timesheet(self):
        response = self.client_for(self.master_user).get(
            reverse('staff-timesheet'), {'staff': self.anita.id, 'week': '2026-09-01'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['staff_name'], 'Anita')

    def test_the_timesheet_requires_signing_in(self):
        anonymous = APIClient()
        anonymous.credentials(HTTP_X_TENANT_ID=self.tenant.schema_name)
        response = anonymous.get(reverse('staff-timesheet'))
        self.assertIn(response.status_code, (401, 403))

    def test_a_corrected_row_is_marked_as_corrected(self):
        session = AttendanceSession.objects.filter(staff=self.anita).first()
        self.client_for(self.owner).post(
            reverse('staff-attendance-correct', args=[session.id]),
            {'check_in': '2026-09-02T08:00:00', 'reason': 'Early start'},
            format='json')
        response = self.client_for(self.owner).get(
            reverse('staff-timesheet'), {'staff': self.anita.id, 'week': '2026-09-01'})
        corrected = [s for s in response.data['sessions'] if s['was_corrected']]
        self.assertEqual(len(corrected), 1)


class AttendanceStaysFinanciallyNeutralTests(AttendanceTestCase):
    def test_attendance_never_reports_money(self):
        """Phase 3 answers minutes. Multiplying them by a rate is Phase 4."""
        self.terms_for(self.anita, hourly_rate=Decimal('120.00'))
        session = AttendanceSession.objects.create(
            staff=self.anita, date=date(2026, 9, 1),
            check_in=self._at(2026, 9, 1, 9, 0),
            check_out=self._at(2026, 9, 1, 17, 0), minutes=480)
        response = self.client_for(self.owner).get(
            reverse('staff-attendance-detail', args=[session.id]))
        body = response.content.decode()
        for money_word in ('hourly_rate', 'gross', 'earnings', 'net_pay', 'deduction'):
            self.assertNotIn(money_word, body)


# =============================================================================
# PHASE 7 -- performance, reviews and role KPIs
# =============================================================================

from datetime import timedelta as _td  # noqa: E402

from . import performance  # noqa: E402
from .models import StaffPerformanceReview  # noqa: E402

PERIOD_START = date(2026, 9, 1)
PERIOD_END = date(2026, 9, 30)


class PerformanceTestCase(StaffProfileTestCase):
    """The Phase 1 fixtures plus work and attendance to measure."""

    def profile_for(self, tailor, **extra):
        return StaffProfile.objects.create(staff=tailor, **extra)

    def worked(self, tailor, day, hours=8, month=9):
        s = AttendanceSession(
            staff=tailor, date=date(2026, month, day),
            check_in=datetime(2026, month, day, 9, 0, tzinfo=tenant_timezone()),
            check_out=datetime(2026, month, day, 9 + hours, 0,
                               tzinfo=tenant_timezone()))
        s.minutes = s.duration_minutes()
        s.save()
        return s

    def _customer(self):
        """One reusable customer.

        NOT get_or_create on the number: Customer.save() normalises it to
        international form, so a lookup by the raw string never matches the row
        it just wrote and the second call collides on the unique index.
        """
        from crm_api.models import Customer
        existing = Customer.objects.filter(first_name='Perf').first()
        if existing is not None:
            return existing
        return Customer.objects.create(
            first_name='Perf', last_name='Client', mobile_number='9600000900')

    def stage(self, tailor, day, *, status='COMPLETED', sla=24, elapsed_hours=8,
              performed=True, month=9):
        """One OrderStage assigned to `tailor`, with real timestamps."""
        from crm_api.models import Order, OrderStage
        customer = self._customer()
        order = Order.objects.create(
            order_id=f'T2B-PERF-{OrderStage.objects.count() + 1:04d}',
            customer=customer)
        started = datetime(2026, month, day, 9, 0, tzinfo=tenant_timezone())
        completed = (started + _td(hours=elapsed_hours)
                     if status == 'COMPLETED' else None)
        return OrderStage.objects.create(
            order=order, stage_key='stitching_in_progress',
            stage_name='Stitching', status=status,
            started_at=started, completed_at=completed,
            assigned_to=tailor,
            performed_by=tailor if (performed and status == 'COMPLETED') else None,
            sla_hours=sla)

    def metrics(self, tailor, start=PERIOD_START, end=PERIOD_END):
        return performance.staff_metrics(tailor, start, end)


class AttendanceKpiTests(PerformanceTestCase):
    def test_hours_and_days_come_from_attendance_sessions(self):
        self.profile_for(self.anita)
        self.worked(self.anita, 1, hours=8)
        self.worked(self.anita, 2, hours=9)
        m = self.metrics(self.anita)['attendance']
        self.assertEqual(m['days_attended']['value'], 2)
        self.assertEqual(m['worked_minutes']['value'], 1020)
        self.assertEqual(m['worked_hours']['value'], 17.0)
        self.assertEqual(m['average_hours_per_day']['value'], 8.5)

    def test_no_attendance_is_unavailable_not_zero_hours(self):
        """"No data" and "worked nothing" are different claims."""
        self.profile_for(self.anita)
        m = self.metrics(self.anita)['attendance']
        self.assertFalse(m['worked_hours']['available'])
        self.assertIsNone(m['worked_hours']['value'])
        self.assertFalse(m['average_hours_per_day']['available'])
        # A count of days IS meaningful at zero.
        self.assertEqual(m['days_attended']['value'], 0)

    def test_an_open_session_is_reported_and_pays_no_hours(self):
        self.profile_for(self.anita)
        AttendanceSession.objects.create(
            staff=self.anita, date=date(2026, 9, 3),
            check_in=datetime(2026, 9, 3, 9, 0, tzinfo=tenant_timezone()))
        m = self.metrics(self.anita)['attendance']
        self.assertEqual(m['open_sessions']['value'], 1)
        self.assertFalse(m['worked_hours']['available'])

    def test_attendance_outside_the_period_is_excluded(self):
        self.profile_for(self.anita)
        self.worked(self.anita, 5, month=8)
        self.worked(self.anita, 2, month=9)
        m = self.metrics(self.anita)['attendance']
        self.assertEqual(m['days_attended']['value'], 1)


class ProductivityKpiTests(PerformanceTestCase):
    def test_work_in_the_period_and_completed_come_from_order_stages(self):
        self.profile_for(self.anita)
        self.stage(self.anita, 2)
        self.stage(self.anita, 3)
        self.stage(self.anita, 4, status='IN_PROGRESS')
        m = self.metrics(self.anita)['productivity']
        self.assertEqual(m['in_period']['value'], 3)
        self.assertEqual(m['completed']['value'], 2)
        self.assertAlmostEqual(m['completion_rate']['value'], 66.7, places=1)

    def test_no_work_in_the_period_is_unavailable_not_zero_percent(self):
        """0% would say they failed work they were never given."""
        self.profile_for(self.anita)
        m = self.metrics(self.anita)['productivity']
        self.assertFalse(m['completion_rate']['available'])
        self.assertIsNone(m['completion_rate']['value'])
        self.assertEqual(m['in_period']['value'], 0)

    def test_work_finished_by_somebody_else_is_visible_as_a_gap(self):
        self.profile_for(self.anita)
        self.stage(self.anita, 2, performed=True)
        self.stage(self.anita, 3, performed=False)
        m = self.metrics(self.anita)['productivity']
        self.assertEqual(m['completed']['value'], 2)
        self.assertEqual(m['performed_by_them']['value'], 1)

    def test_completion_rate_is_never_a_division_by_zero(self):
        self.profile_for(self.anita)
        m = self.metrics(self.anita)
        for group in ('productivity', 'timeliness', 'reliability'):
            for metric in m[group].values():
                self.assertIsInstance(metric, dict)


class TimelinessKpiTests(PerformanceTestCase):
    def test_on_time_is_measured_against_the_stage_sla(self):
        self.profile_for(self.anita)
        self.stage(self.anita, 2, sla=24, elapsed_hours=8)     # on time
        self.stage(self.anita, 3, sla=24, elapsed_hours=30)    # 6h late
        m = self.metrics(self.anita)['timeliness']
        self.assertEqual(m['measured']['value'], 2)
        self.assertEqual(m['on_time']['value'], 1)
        self.assertEqual(m['overdue']['value'], 1)
        self.assertEqual(m['on_time_rate']['value'], 50.0)
        self.assertEqual(m['average_delay_hours']['value'], 6.0)

    def test_no_completed_work_is_unavailable_not_zero(self):
        self.profile_for(self.anita)
        self.stage(self.anita, 2, status='IN_PROGRESS')
        m = self.metrics(self.anita)['timeliness']
        self.assertFalse(m['on_time_rate']['available'])
        self.assertFalse(m['average_delay_hours']['available'])

    def test_delay_averages_only_the_late_work(self):
        self.profile_for(self.anita)
        self.stage(self.anita, 2, sla=24, elapsed_hours=8)
        self.stage(self.anita, 3, sla=24, elapsed_hours=8)
        self.stage(self.anita, 4, sla=24, elapsed_hours=34)   # 10h late
        m = self.metrics(self.anita)['timeliness']
        self.assertEqual(m['average_delay_hours']['value'], 10.0)

    def test_a_stage_with_no_sla_is_not_counted_late(self):
        """No promise was made, so none can have been broken.

        This used to read a missing sla_hours as a deadline of zero, which made
        every such stage overdue the moment it started -- lateness manufactured
        out of an absent target, and put on somebody's review.
        """
        self.profile_for(self.anita)
        self.stage(self.anita, 2, sla=0, elapsed_hours=8)
        m = self.metrics(self.anita)['timeliness']
        self.assertEqual(m['measured']['value'], 0)
        self.assertEqual(m['overdue']['value'], 0)
        self.assertFalse(m['on_time_rate']['available'])

    def test_stages_without_an_sla_leave_the_rate_to_the_ones_that_have_one(self):
        self.profile_for(self.anita)
        self.stage(self.anita, 2, sla=24, elapsed_hours=8)     # on time
        self.stage(self.anita, 3, sla=0, elapsed_hours=99)     # no promise
        m = self.metrics(self.anita)['timeliness']
        self.assertEqual(m['measured']['value'], 1)
        self.assertEqual(m['on_time_rate']['value'], 100.0)

    def test_timeliness_and_reliability_agree_about_a_missing_sla(self):
        """The two used to disagree: reliability skipped it, timeliness did not."""
        self.profile_for(self.anita)
        self.stage(self.anita, 2, sla=0, status='IN_PROGRESS')
        full = self.metrics(self.anita)
        self.assertEqual(full['timeliness']['overdue']['value'], 0)
        self.assertEqual(
            full['reliability']['overdue_open_assignments']['value'], 0)

    def test_only_stages_touching_the_period_are_read_from_the_database(self):
        """The window is narrowed in SQL, not after loading a whole career.

        Assigned work outside the period must not be fetched at all, or the
        cost of asking about one week grows with the person's entire tenure.
        """
        self.profile_for(self.anita)
        self.stage(self.anita, 2, month=9)
        for day in (3, 4, 5, 6, 7):
            self.stage(self.anita, day, month=6)
        rows = performance._stages_in_window(
            self.anita, PERIOD_START, PERIOD_END)
        self.assertEqual(len(rows), 1)
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as ctx:
            performance._stages_in_window(self.anita, PERIOD_START, PERIOD_END)
        sql = ' '.join(q['sql'] for q in ctx.captured_queries)
        self.assertIn('completed_at', sql, 'the period must be filtered in SQL')


class Phase7ReviewFixTests(PerformanceTestCase):
    """Regressions for the defects the Phase 7 adversarial review confirmed."""

    def _stage(self, tailor, **kw):
        from crm_api.models import Order, OrderStage
        order = Order.objects.create(
            order_id=f'T2B-RF-{OrderStage.objects.count() + 1:04d}',
            customer=self._customer())
        return OrderStage.objects.create(
            order=order, stage_key='stitching_in_progress',
            stage_name='Stitching', assigned_to=tailor, **kw)

    def test_work_assigned_but_never_started_still_counts_as_outstanding(self):
        """assign_stage writes no timestamp, so this work belonged to no period.

        It reported zero outstanding for someone holding five untouched jobs.
        """
        self.profile_for(self.anita)
        for _ in range(5):
            self._stage(self.anita, status='NOT_STARTED')
        m = self.metrics(self.anita)
        self.assertEqual(m['reliability']['outstanding_assignments']['value'], 5)

    def test_an_open_stage_started_before_the_window_is_still_outstanding(self):
        """The oldest job in the boutique is exactly the one to surface."""
        self.profile_for(self.anita)
        self._stage(self.anita, status='IN_PROGRESS', sla_hours=24,
                    started_at=datetime(2026, 6, 1, 9, 0, tzinfo=tenant_timezone()))
        m = self.metrics(self.anita)
        self.assertEqual(m['reliability']['outstanding_assignments']['value'], 1)
        self.assertEqual(m['reliability']['overdue_open_assignments']['value'], 1)

    def test_a_skipped_stage_is_neither_a_success_nor_a_failure(self):
        """It used to drag completion down while consistency called it done."""
        self.profile_for(self.anita)
        self.stage(self.anita, 2, status='COMPLETED')
        self.stage(self.anita, 3, status='SKIPPED')
        m = self.metrics(self.anita)
        self.assertEqual(m['productivity']['completion_rate']['value'], 100.0)
        self.assertEqual(m['reliability']['completion_consistency']['value'], 100.0)

    def test_overdue_open_is_judged_at_the_period_end_not_the_wall_clock(self):
        """A closed period must not keep growing new lateness."""
        self.profile_for(self.anita)
        self._stage(self.anita, status='IN_PROGRESS', sla_hours=96,
                    started_at=datetime(2026, 9, 30, 18, 0,
                                        tzinfo=tenant_timezone()))
        m = self.metrics(self.anita, date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual(m['reliability']['overdue_open_assignments']['value'], 0)

    def test_not_employed_reports_the_period_that_was_asked_for(self):
        """It used to answer with a period ending before it started."""
        profile = self.profile_for(self.anita)
        profile.joined_at = date(2026, 12, 1)
        profile.save()
        m = self.metrics(self.anita, date(2026, 9, 1), date(2026, 9, 30))
        self.assertFalse(m['employed_in_period'])
        self.assertLessEqual(m['period_start'], m['period_end'])

    def test_worked_minutes_and_worked_hours_give_the_same_answer(self):
        """One fact in two units must not be available in one and not the other."""
        self.profile_for(self.anita)
        a = self.metrics(self.anita)['attendance']
        self.assertEqual(a['worked_minutes']['available'],
                         a['worked_hours']['available'])
        # A count of days IS meaningful at zero, and stays available.
        self.assertTrue(a['days_attended']['available'])

    def test_inspecting_someone_elses_work_is_not_your_own_rework_rate(self):
        from apps.production.models import ProductionTask, QCRecord
        from crm_api.models import Order
        self.profile_for(self.anita)
        order = Order.objects.create(order_id='T2B-RF-QC1',
                                     customer=self._customer())
        task = ProductionTask.objects.create(
            order=order, title='Stitch', stage_key='stitching_in_progress',
            assigned_to=self.balan)
        for _ in range(3):
            QCRecord.objects.create(order=order, task=task,
                                    inspector=self.anita,
                                    status='REWORK_REQUIRED')
        q = self.metrics(self.anita)['quality']
        # She did the inspecting; the defects are not hers.
        self.assertEqual(q['inspected']['value'], 3)
        self.assertFalse(q['rework_rate']['available'])


class QualityKpiTests(PerformanceTestCase):
    def test_quality_is_reported_unavailable_not_fabricated(self):
        """With no QC records for this person, a rate would be invented."""
        self.profile_for(self.anita)
        self.stage(self.anita, 2)
        m = self.metrics(self.anita)['quality']
        for key in ('pass_rate', 'rework_rate', 'passed', 'rework'):
            self.assertFalse(m[key]['available'], key)
            self.assertIsNone(m[key]['value'], key)
        self.assertIn('No quality checks were recorded', m['pass_rate']['reason'])

    def test_the_qc_endpoint_exists_so_the_premise_is_not_that_it_cannot(self):
        """Phase 7 first claimed nothing in the app can create a QCRecord.

        That was wrong -- /api/production/qc/ is a ModelViewSet with a
        perform_create -- and the test that "proved" it merely counted rows in
        an empty test database, which any empty table passes. What is actually
        true is that no screen posts there, so the table is usually empty. This
        asserts the writable endpoint exists, so nobody restores the old claim.
        """
        from rest_framework.routers import DefaultRouter
        from apps.production.urls import router
        self.assertIsInstance(router, DefaultRouter)
        registered = {prefix for prefix, _viewset, _basename in router.registry}
        self.assertIn('qc', registered)

    def test_quality_reports_real_figures_once_records_exist(self):
        """The queries are real; the source is merely empty on most boutiques."""
        from apps.production.models import ProductionTask, QCRecord
        from crm_api.models import Customer, Order
        self.profile_for(self.anita)
        customer = Customer.objects.create(
            first_name='Q', last_name='C', mobile_number='9600000901')
        order = Order.objects.create(order_id='T2B-QC-0001', customer=customer)
        task = ProductionTask.objects.create(
            order=order, title='Stitch', stage_key='stitching_in_progress',
            assigned_to=self.anita)
        QCRecord.objects.create(order=order, task=task, status='PASSED')
        QCRecord.objects.create(order=order, task=task, status='REWORK_REQUIRED')
        m = self.metrics(self.anita)['quality']
        self.assertTrue(m['pass_rate']['available'])
        # Her work was checked twice; she inspected nothing herself.
        self.assertEqual(m['checked']['value'], 2)
        self.assertEqual(m['inspected']['value'], 0)
        self.assertEqual(m['pass_rate']['value'], 50.0)
        self.assertEqual(m['rework_rate']['value'], 50.0)


class EmploymentWindowKpiTests(PerformanceTestCase):
    def test_someone_who_joined_midway_is_measured_from_their_joining_day(self):
        self.profile_for(self.anita, joined_at=date(2026, 9, 15))
        self.worked(self.anita, 2)     # before joining
        self.worked(self.anita, 20)    # after joining
        m = self.metrics(self.anita)
        self.assertEqual(m['period_start'], date(2026, 9, 15))
        self.assertEqual(m['attendance']['days_attended']['value'], 1)

    def test_someone_who_left_midway_is_not_measured_afterwards(self):
        self.profile_for(self.anita, joined_at=date(2026, 1, 1),
                         exit_date=date(2026, 9, 10))
        self.worked(self.anita, 5)
        self.worked(self.anita, 20)
        m = self.metrics(self.anita)
        self.assertEqual(m['period_end'], date(2026, 9, 10))
        self.assertEqual(m['attendance']['days_attended']['value'], 1)

    def test_someone_not_employed_in_the_period_reports_no_data(self):
        self.profile_for(self.anita, joined_at=date(2026, 12, 1))
        self.worked(self.anita, 2)
        m = self.metrics(self.anita)
        self.assertFalse(m['employed_in_period'])
        self.assertFalse(m['attendance']['worked_hours']['available'])
        self.assertIn('Not employed', m['attendance']['worked_hours']['reason'])


class RoleKpiTests(PerformanceTestCase):
    def test_each_role_gets_its_own_headline_metrics(self):
        self.assertNotEqual(performance.kpis_for_role('QC Master'),
                            performance.kpis_for_role('Tailor'))
        self.assertIn('quality.pass_rate', performance.kpis_for_role('QC Master'))
        self.assertIn('quality.rework_rate', performance.kpis_for_role('Tailor'))

    def test_an_unknown_role_falls_back_rather_than_failing(self):
        self.assertEqual(performance.kpis_for_role('Nightwatchman'),
                         performance.DEFAULT_KPIS)

    def test_every_shipped_role_has_a_kpi_set(self):
        from crm_api.models import Tailor as T
        for role, _label in T.ROLE_CHOICES:
            self.assertIn(role, performance.ROLE_KPIS, role)

    def test_headline_reads_the_same_numbers_as_the_detail(self):
        self.profile_for(self.anita)
        self.worked(self.anita, 2, hours=8)
        m = self.metrics(self.anita)
        headline = performance.headline_kpis(m)
        hours = [h for h in headline if h['key'] == 'attendance.worked_hours'][0]
        self.assertEqual(hours['value'], m['attendance']['worked_hours']['value'])


class ReviewLifecycleTests(PerformanceTestCase):
    def _create(self, **extra):
        payload = {'staff': self.anita.id, 'review_type': 'MONTHLY',
                   'period_start': '2026-09-01', 'period_end': '2026-09-30',
                   'productivity_rating': 4, 'attendance_rating': 5}
        payload.update(extra)
        return self.client_for(self.owner).post(
            reverse('staff-review-list'), payload, format='json')

    def test_a_review_must_name_somebody(self):
        """The FK is nullable so a review SURVIVES roster deletion.

        DRF inferred default=None from the unique constraint, so omitting staff
        created a review about nobody that finalise then froze with an empty
        snapshot.
        """
        api = self.client_for(self.owner)
        response = api.post(reverse('staff-review-list'), {
            'review_type': 'MONTHLY', 'period_start': '2026-09-01',
            'period_end': '2026-09-30', 'productivity_rating': 4},
            format='json')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('staff', response.data)

    def test_an_impossible_date_is_rejected_not_a_server_error(self):
        """parse_date RAISES on 2026-02-30; it returns None only on garbage."""
        api = self.client_for(self.owner)
        for query in ('since=2026-02-30', 'until=2026-13-01'):
            response = api.get(f"{reverse('staff-review-list')}?{query}")
            self.assertLess(response.status_code, 500, query)
        response = api.get(
            f"{reverse('staff-performance')}?start=2026-02-30&end=2026-03-31")
        self.assertEqual(response.status_code, 400, response.data)

    def test_owner_creates_a_draft_review(self):
        self.profile_for(self.anita)
        response = self._create()
        self.assertEqual(response.status_code, 201, response.data)
        review = StaffPerformanceReview.objects.get()
        self.assertEqual(review.status, 'DRAFT')
        self.assertEqual(review.staff_name_snapshot, 'Anita')
        self.assertEqual(review.role_snapshot, 'Tailor')
        self.assertEqual(review.reviewer, self.owner)

    def test_the_overall_score_is_the_mean_of_what_was_rated(self):
        self.profile_for(self.anita)
        self._create(productivity_rating=4, attendance_rating=5)
        self.assertEqual(StaffPerformanceReview.objects.get().overall_rating,
                         Decimal('4.5'))

    def test_unrated_components_are_omitted_not_counted_as_zero(self):
        self.profile_for(self.anita)
        self._create(productivity_rating=4, quality_rating=None,
                     attendance_rating=None)
        self.assertEqual(StaffPerformanceReview.objects.get().overall_rating,
                         Decimal('4.0'))

    def test_a_review_with_no_ratings_has_no_score(self):
        self.profile_for(self.anita)
        self._create(productivity_rating=None, attendance_rating=None)
        self.assertIsNone(StaffPerformanceReview.objects.get().overall_rating)

    def test_a_period_that_ends_before_it_starts_is_refused(self):
        self.profile_for(self.anita)
        response = self._create(period_start='2026-09-30', period_end='2026-09-01')
        self.assertEqual(response.status_code, 400)
        self.assertIn('period_end', response.data)

    def test_the_database_refuses_a_backwards_period(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            StaffPerformanceReview.objects.create(
                staff=self.anita, staff_name_snapshot='Anita',
                period_start=date(2026, 9, 30), period_end=date(2026, 9, 1))

    def test_an_invalid_rating_is_refused(self):
        self.profile_for(self.anita)
        for bad in (0, 6, 99):
            response = self._create(productivity_rating=bad)
            self.assertEqual(response.status_code, 400, bad)

    def test_a_non_numeric_rating_is_a_400_not_a_500(self):
        self.profile_for(self.anita)
        for bad in ('excellent', {'x': 1}, [4]):
            response = self._create(productivity_rating=bad)
            self.assertEqual(response.status_code, 400, bad)

    def test_an_unknown_staff_member_is_refused(self):
        response = self._create(staff=999999)
        self.assertEqual(response.status_code, 400)

    def test_one_review_per_person_per_period_and_type(self):
        self.profile_for(self.anita)
        self.assertEqual(self._create().status_code, 201)
        self.assertEqual(self._create().status_code, 400)

    def test_a_draft_can_be_edited(self):
        self.profile_for(self.anita)
        review_id = self._create().data['id']
        response = self.client_for(self.owner).patch(
            reverse('staff-review-detail', args=[review_id]),
            {'productivity_rating': 2, 'strengths': 'Steady hand'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        review = StaffPerformanceReview.objects.get()
        self.assertEqual(review.productivity_rating, 2)
        self.assertEqual(review.overall_rating, Decimal('3.5'))

    def test_there_is_no_delete(self):
        self.profile_for(self.anita)
        review_id = self._create().data['id']
        response = self.client_for(self.owner).delete(
            reverse('staff-review-detail', args=[review_id]))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(StaffPerformanceReview.objects.count(), 1)


class ReviewFinalisationTests(PerformanceTestCase):
    def setUp(self):
        super().setUp()
        self.profile_for(self.anita)
        self.worked(self.anita, 2, hours=8)
        self.stage(self.anita, 3, sla=24, elapsed_hours=8)
        self.review = StaffPerformanceReview.objects.create(
            staff=self.anita, staff_name_snapshot='Anita', role_snapshot='Tailor',
            period_start=PERIOD_START, period_end=PERIOD_END,
            productivity_rating=4, attendance_rating=4)

    def _finalise(self, client=None):
        return (client or self.client_for(self.owner)).post(
            reverse('staff-review-finalise', args=[self.review.id]), {},
            format='json')

    def test_finalise_does_not_re_label_the_review_with_a_later_role(self):
        """The role is stamped at creation so a promotion cannot re-label it.

        finalise() then overwrote it from the live roster, so a Tailor promoted
        between draft and finalise had her Tailor period filed as a Master's.
        """
        self.anita.role = 'Master'
        self.anita.save(update_fields=['role'])
        self._finalise()
        self.review.refresh_from_db()
        self.assertEqual(self.review.role_snapshot, 'Tailor')

    def test_a_patch_cannot_un_finalise_a_review_it_raced(self):
        """DRF loads the row, THEN validates, THEN saves.

        The serializer's is_final guard judged a copy read before the finalise
        committed, so the PATCH wrote its whole stale row back -- restoring
        DRAFT, clearing finalised_at and wiping the frozen snapshot.
        """
        api = self.client_for(self.owner)
        url = reverse('staff-review-detail', args=[self.review.id])
        stale = StaffPerformanceReview.objects.get(pk=self.review.pk)
        self._finalise()
        # Re-issue the PATCH built against the pre-finalise state.
        self.assertEqual(stale.status, 'DRAFT')
        response = api.patch(url, {'manager_notes': 'late note'}, format='json')
        self.assertIn(response.status_code, (400, 409), response.data)
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, 'FINAL')
        self.assertIsNotNone(self.review.finalised_at)
        self.assertNotEqual(self.review.kpi_snapshot, {})

    def test_acknowledging_does_not_name_the_reviewee_in_the_feed(self):
        """UniversalActivity is readable by Masters; an assessment is not."""
        from apps.activities.models import UniversalActivity
        self._finalise()
        self.client_for(self.anita_user).post(
            reverse('staff-review-acknowledge', args=[self.review.id]), {},
            format='json')
        rows = UniversalActivity.objects.filter(action='REVIEW_ACKNOWLEDGED')
        self.assertTrue(rows.exists())
        for row in rows:
            self.assertNotIn('Anita', row.user_name_snapshot)
            self.assertNotIn('Anita', row.title)
            self.assertNotIn('Anita', row.description or '')
            self.assertIsNone(row.user)

    def test_finalise_and_acknowledge_move_updated_at(self):
        before = self.review.updated_at
        self._finalise()
        self.review.refresh_from_db()
        self.assertGreater(self.review.updated_at, before)

    def test_finalising_freezes_the_metrics(self):
        response = self._finalise()
        self.assertEqual(response.status_code, 200, response.data)
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, 'FINAL')
        self.assertIsNotNone(self.review.finalised_at)
        snap = self.review.kpi_snapshot
        self.assertEqual(snap['attendance']['worked_hours']['value'], 8.0)
        self.assertEqual(snap['productivity']['completed']['value'], 1)

    def test_later_work_does_not_change_a_finalised_review(self):
        self._finalise()
        before = dict(self.review.kpi_snapshot) if self.review.kpi_snapshot else {}
        self.review.refresh_from_db()
        before = self.review.kpi_snapshot
        self.worked(self.anita, 20, hours=10)
        self.stage(self.anita, 21, sla=24, elapsed_hours=40)
        self.review.refresh_from_db()
        self.assertEqual(self.review.kpi_snapshot, before)
        self.assertEqual(self.review.kpi_snapshot['attendance']['worked_hours']['value'],
                         8.0)

    def test_a_role_change_does_not_rewrite_history(self):
        self._finalise()
        self.anita.role = 'Master'
        self.anita.save()
        self.review.refresh_from_db()
        self.assertEqual(self.review.role_snapshot, 'Tailor')

    def test_a_finalised_review_cannot_be_patched(self):
        self._finalise()
        response = self.client_for(self.owner).patch(
            reverse('staff-review-detail', args=[self.review.id]),
            {'productivity_rating': 1}, format='json')
        self.assertEqual(response.status_code, 400)
        self.review.refresh_from_db()
        self.assertEqual(self.review.productivity_rating, 4)

    def test_finalising_twice_is_refused(self):
        self.assertEqual(self._finalise().status_code, 200)
        second = self._finalise()
        self.assertEqual(second.status_code, 409)
        self.assertIn('already been finalised', second.data['error'])

    def test_a_master_cannot_finalise(self):
        master_user = User.objects.create_user(
            username='mira@staff.test', email='mira@staff.test',
            password='mirapass12345')
        Tailor.objects.create(name='Mira', specialty='Supervision', role='Master',
                              email='mira@staff.test', user=master_user)
        self.assertEqual(self._finalise(self.client_for(master_user)).status_code, 403)
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, 'DRAFT')

    def test_a_tailor_cannot_finalise_their_own_review(self):
        self.assertEqual(self._finalise(self.client_for(self.anita_user)).status_code,
                         403)

    def test_the_staff_member_acknowledges_explicitly(self):
        self._finalise()
        response = self.client_for(self.anita_user).post(
            reverse('staff-review-acknowledge', args=[self.review.id]), {},
            format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, 'ACKNOWLEDGED')
        self.assertIsNotNone(self.review.acknowledged_at)

    def test_reading_a_review_is_not_acknowledgement(self):
        self._finalise()
        self.client_for(self.anita_user).get(
            reverse('staff-review-detail', args=[self.review.id]))
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, 'FINAL')

    def test_a_colleague_cannot_acknowledge_it(self):
        self._finalise()
        response = self.client_for(self.balan_user).post(
            reverse('staff-review-acknowledge', args=[self.review.id]), {},
            format='json')
        self.assertIn(response.status_code, (403, 404))

    def test_a_draft_cannot_be_acknowledged(self):
        response = self.client_for(self.anita_user).post(
            reverse('staff-review-acknowledge', args=[self.review.id]), {},
            format='json')
        self.assertIn(response.status_code, (403, 404, 409))

    def test_history_survives_the_staff_member_being_deleted(self):
        self._finalise()
        self.anita.delete()
        self.review.refresh_from_db()
        self.assertIsNone(self.review.staff)
        self.assertEqual(self.review.staff_name_snapshot, 'Anita')
        self.assertEqual(self.review.role_snapshot, 'Tailor')
        self.assertEqual(
            self.review.kpi_snapshot['attendance']['worked_hours']['value'], 8.0)

    def test_the_activity_feed_carries_no_rating_or_metric(self):
        self._finalise()
        for entry in UniversalActivity.objects.filter(
                entity_type='StaffPerformanceReview'):
            blob = f"{entry.title} {entry.description} {entry.new_value}"
            for leak in ('Anita', '4', '8.0', 'rating'):
                self.assertNotIn(leak, blob.replace('REVIEW_', ''), leak)


class PerformanceAccessTests(PerformanceTestCase):
    def setUp(self):
        super().setUp()
        self.profile_for(self.anita, hourly_rate=Decimal('120.00'),
                         deposit_total=Decimal('5000.00'),
                         deposit_weekly=Decimal('500.00'))
        self.profile_for(self.balan, hourly_rate=Decimal('999.00'))
        self.worked(self.anita, 2)
        self.worked(self.balan, 2)
        self.master_user = User.objects.create_user(
            username='mira@staff.test', email='mira@staff.test',
            password='mirapass12345')
        self.master = Tailor.objects.create(
            name='Mira', specialty='Supervision', role='Master',
            email='mira@staff.test', user=self.master_user)
        self.review = StaffPerformanceReview.objects.create(
            staff=self.anita, staff_name_snapshot='Anita', role_snapshot='Tailor',
            period_start=PERIOD_START, period_end=PERIOD_END,
            productivity_rating=4, status='FINAL',
            finalised_at=timezone.now())

    def test_owner_sees_the_whole_team(self):
        response = self.client_for(self.owner).get(
            reverse('staff-performance'),
            {'start': '2026-09-01', 'end': '2026-09-30'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['staff_count'], 2)

    def test_a_master_sees_team_operational_performance(self):
        response = self.client_for(self.master_user).get(
            reverse('staff-performance'),
            {'start': '2026-09-01', 'end': '2026-09-30'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['staff_count'], 2)

    def test_the_performance_payload_carries_no_financial_field_at_all(self):
        """The guarantee is structural: performance.py cannot see money."""
        for who in (self.owner, self.master_user):
            body = self.client_for(who).get(
                reverse('staff-performance'),
                {'start': '2026-09-01', 'end': '2026-09-30'}).content.decode()
            for leak in ('hourly_rate', 'deposit_total', 'deposit_weekly',
                         'gross_earnings', 'net_payable', 'payout',
                         'advance', '120.00', '999.00', '5000.00'):
                self.assertNotIn(leak, body, leak)

    def test_a_tailor_sees_only_their_own_performance(self):
        response = self.client_for(self.anita_user).get(
            reverse('staff-performance'),
            {'start': '2026-09-01', 'end': '2026-09-30'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['staff_count'], 1)
        self.assertEqual(response.data['results'][0]['staff_name'], 'Anita')

    def test_a_tailor_cannot_widen_scope_with_the_staff_parameter(self):
        response = self.client_for(self.anita_user).get(
            reverse('staff-performance'),
            {'start': '2026-09-01', 'end': '2026-09-30', 'staff': self.balan.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['staff_count'], 1)
        self.assertEqual(response.data['results'][0]['staff_name'], 'Anita')
        self.assertNotIn('Balan', response.content.decode())

    def test_a_master_cannot_read_reviews(self):
        """Supervising the floor does not include reading its assessments."""
        listing = self.client_for(self.master_user).get(reverse('staff-review-list'))
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data, [])
        detail = self.client_for(self.master_user).get(
            reverse('staff-review-detail', args=[self.review.id]))
        self.assertEqual(detail.status_code, 404)

    def test_a_master_cannot_write_a_review(self):
        response = self.client_for(self.master_user).post(
            reverse('staff-review-list'),
            {'staff': self.anita.id, 'period_start': '2026-10-01',
             'period_end': '2026-10-31'}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_a_tailor_reads_their_own_finalised_review_only(self):
        draft = StaffPerformanceReview.objects.create(
            staff=self.anita, staff_name_snapshot='Anita',
            period_start=date(2026, 10, 1), period_end=date(2026, 10, 31),
            review_type='MONTHLY', status='DRAFT')
        listing = self.client_for(self.anita_user).get(reverse('staff-review-list'))
        self.assertEqual([r['id'] for r in listing.data], [str(self.review.id)])
        self.assertEqual(self.client_for(self.anita_user).get(
            reverse('staff-review-detail', args=[draft.id])).status_code, 404)

    def test_a_tailor_cannot_read_a_colleagues_review(self):
        other = StaffPerformanceReview.objects.create(
            staff=self.balan, staff_name_snapshot='Balan',
            period_start=PERIOD_START, period_end=PERIOD_END,
            status='FINAL', finalised_at=timezone.now())
        response = self.client_for(self.anita_user).get(
            reverse('staff-review-detail', args=[other.id]))
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('Balan', response.content.decode())

    def test_a_tailor_cannot_write_or_patch_a_review(self):
        anita = self.client_for(self.anita_user)
        self.assertEqual(anita.post(
            reverse('staff-review-list'),
            {'staff': self.anita.id, 'period_start': '2026-11-01',
             'period_end': '2026-11-30'}, format='json').status_code, 403)
        self.assertEqual(anita.patch(
            reverse('staff-review-detail', args=[self.review.id]),
            {'productivity_rating': 5}, format='json').status_code, 403)

    def test_a_designer_gets_no_performance_and_no_reviews(self):
        from apps.design_studio.models import Designer
        user = User.objects.create_user(
            username='dia@staff.test', email='dia@staff.test',
            password='diapass12345')
        Designer.objects.create(name='Dia', email='dia@staff.test', user=user)
        client = self.client_for(user)
        perf = client.get(reverse('staff-performance'),
                          {'start': '2026-09-01', 'end': '2026-09-30'})
        self.assertEqual(perf.status_code, 200)
        self.assertEqual(perf.data['staff_count'], 0)
        self.assertEqual(client.get(reverse('staff-review-list')).data, [])

    def test_anonymous_gets_nothing(self):
        anonymous = APIClient()
        anonymous.credentials(HTTP_X_TENANT_ID=self.tenant.schema_name)
        for url in (reverse('staff-performance'), reverse('staff-review-list')):
            self.assertIn(anonymous.get(url).status_code, (401, 403), url)

    def test_a_malformed_period_is_a_400_not_a_500(self):
        response = self.client_for(self.owner).get(
            reverse('staff-performance'),
            {'start': '2026-09-30', 'end': '2026-09-01'})
        self.assertEqual(response.status_code, 400)

    def test_garbage_filters_do_not_error(self):
        owner = self.client_for(self.owner)
        for params in ({'start': 'yesterday'}, {'staff': 'abc'},
                       {'role': "'; DROP TABLE crm_api_tailor; --"},
                       {'start': '2026-09-01', 'end': '2026-09-30', 'staff': 'x'}):
            self.assertEqual(owner.get(reverse('staff-performance'),
                                       params).status_code, 200, params)
        for params in ({'staff': 'abc'}, {'status': 'NONSENSE'},
                       {'since': 'never'}):
            self.assertEqual(owner.get(reverse('staff-review-list'),
                                       params).status_code, 200, params)


class PerformanceQueryEfficiencyTests(PerformanceTestCase):
    def _dashboard_queries(self):
        from django.test.utils import CaptureQueriesContext
        owner = self.client_for(self.owner)
        with CaptureQueriesContext(connection) as captured:
            owner.get(reverse('staff-performance'),
                      {'start': '2026-09-01', 'end': '2026-09-30'})
        return len(captured)

    def _add_staff(self, n, offset=0):
        for i in range(n):
            tailor = Tailor.objects.create(
                name=f'Worker {offset + i}', specialty='Stitching', role='Tailor')
            self.profile_for(tailor)
            self.worked(tailor, 2)
            self.stage(tailor, 3)

    def test_the_dashboard_query_count_grows_gently_with_staff(self):
        """Measured, not asserted against a magic number.

        A per-person fan-out is what makes a dashboard unusable at twenty
        people, so what matters is the SLOPE. Each staff member costs a small
        bounded number of queries; this pins that it stays bounded rather than
        multiplying.
        """
        self._add_staff(2)
        two = self._dashboard_queries()
        self._add_staff(6, offset=2)
        eight = self._dashboard_queries()
        per_staff = (eight - two) / 6
        self.assertLess(per_staff, 8,
                        f'{per_staff:.1f} queries per staff member is a fan-out')


class CrossTenantPerformanceTests(TransactionTestCase):
    """Two real boutique schemas. Performance and reviews must not cross."""

    def setUp(self):
        connection.set_schema_to_public()
        self.alpha = self._boutique('perf_alpha', 'owner@perfa.test', 'Alpha')
        self.beta = self._boutique('perf_beta', 'owner@perfb.test', 'Beta')
        self._seed(self.alpha, 'Alpha Worker', 111)
        self._seed(self.beta, 'Beta Worker', 222)
        connection.set_schema_to_public()

    def tearDown(self):
        connection.set_schema_to_public()
        for schema in ('perf_alpha', 'perf_beta'):
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
    def _seed(tenant, staff_name, marker):
        with schema_context(tenant.schema_name):
            owner = User.objects.create_user(
                username=tenant.owner_email, email=tenant.owner_email,
                password='ownerpw12345')
            Token.objects.get_or_create(user=owner)
            tailor = Tailor.objects.create(
                name=staff_name, specialty='Stitching', role='Tailor')
            StaffProfile.objects.create(staff=tailor)
            s = AttendanceSession(
                staff=tailor, date=date(2026, 9, 2),
                check_in=datetime(2026, 9, 2, 9, 0, tzinfo=tenant_timezone(tenant)),
                check_out=datetime(2026, 9, 2, 9 + (marker // 111), 0,
                                   tzinfo=tenant_timezone(tenant)))
            s.minutes = s.duration_minutes()
            s.save()
            StaffPerformanceReview.objects.create(
                staff=tailor, staff_name_snapshot=staff_name,
                period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
                status='FINAL', finalised_at=timezone.now(),
                manager_notes=f'marker-{marker}')

    def _client(self, tenant):
        with schema_context(tenant.schema_name):
            token = Token.objects.get(user__email=tenant.owner_email).key
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Token {token}',
                        HTTP_X_TENANT_ID=tenant.schema_name)
        return api

    def test_performance_does_not_cross_tenants(self):
        response = self._client(self.alpha).get(
            reverse('staff-performance'),
            {'start': '2026-09-01', 'end': '2026-09-30'})
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('Alpha Worker', body)
        self.assertNotIn('Beta Worker', body)

    def test_reviews_do_not_cross_tenants(self):
        response = self._client(self.alpha).get(reverse('staff-review-list'))
        body = response.content.decode()
        self.assertIn('marker-111', body)
        self.assertNotIn('marker-222', body)

    def test_a_review_id_from_another_boutique_is_not_found(self):
        with schema_context(self.beta.schema_name):
            beta_review = StaffPerformanceReview.objects.get()
        response = self._client(self.alpha).get(
            reverse('staff-review-detail', args=[beta_review.id]))
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('marker-222', response.content.decode())

    def test_a_reviewer_cannot_reference_another_tenants_staff(self):
        with schema_context(self.beta.schema_name):
            beta_staff = Tailor.objects.get(name='Beta Worker')
        response = self._client(self.alpha).post(
            reverse('staff-review-list'),
            {'staff': beta_staff.id, 'period_start': '2026-10-01',
             'period_end': '2026-10-31'}, format='json')
        # Either the id does not exist in Alpha's schema, or it names a
        # different Alpha row -- never Beta's person.
        if response.status_code == 201:
            self.assertNotEqual(response.data['staff_name_snapshot'], 'Beta Worker')
        else:
            self.assertEqual(response.status_code, 400)


class ConcurrentFinalisationTests(TransactionTestCase):
    """Two tabs pressing Finalise. Only one snapshot may be written."""

    SCHEMA = 'conc_review'

    def setUp(self):
        connection.set_schema_to_public()
        self.tenant = BoutiqueTenant(
            schema_name=self.SCHEMA, owner_email='owner@cr.test',
            name='Review Race', timezone='Asia/Kolkata')
        self.tenant.save()
        with schema_context(self.SCHEMA):
            self.owner = User.objects.create_user(
                username='owner@cr.test', email='owner@cr.test',
                password='ownerpw12345')
            self.staff = Tailor.objects.create(
                name='Racer', specialty='Stitching', role='Tailor')
            StaffProfile.objects.create(staff=self.staff)
            self.review = StaffPerformanceReview.objects.create(
                staff=self.staff, staff_name_snapshot='Racer',
                period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
                productivity_rating=4)

    def tearDown(self):
        connection.set_schema_to_public()
        with connection.cursor() as c:
            c.execute(f'DROP SCHEMA IF EXISTS "{self.SCHEMA}" CASCADE')
        BoutiqueTenant.objects.filter(schema_name=self.SCHEMA).delete()

    def test_two_finalisations_at_once_produce_one(self):
        import threading
        from rest_framework.test import APIClient as Client

        with schema_context(self.SCHEMA):
            token = Token.objects.create(user=self.owner).key

        barrier = threading.Barrier(2)
        codes = []

        def finalise():
            try:
                api = Client()
                api.credentials(HTTP_AUTHORIZATION=f'Token {token}',
                                HTTP_X_TENANT_ID=self.SCHEMA)
                barrier.wait(timeout=10)
                codes.append(api.post(
                    reverse('staff-review-finalise', args=[self.review.id]),
                    {}, format='json').status_code)
            finally:
                connection.close()

        threads = [threading.Thread(target=finalise) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        with schema_context(self.SCHEMA):
            review = StaffPerformanceReview.objects.get(pk=self.review.pk)
            self.assertEqual(review.status, 'FINAL')
            self.assertEqual(StaffPerformanceReview.objects.filter(
                status='FINAL').count(), 1)
        self.assertEqual(sorted(codes), [200, 409])
