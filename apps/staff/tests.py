"""Employment terms, and who may see them.

The test this file exists for is `test_a_tailor_cannot_read_a_colleagues_rate`.
Everything else here is ordinary CRUD cover; that one is the reason the model was
put in its own table instead of onto Tailor, and it is the assertion that will
fail if a later phase ever publishes these columns through the roster.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test import TransactionTestCase
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from crm_api.models import Tailor
from tenants.models import BoutiqueTenant

from .models import StaffProfile
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
