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
from django.db import IntegrityError, connection
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
