"""Employment terms, and who may see them.

The test this file exists for is `test_a_tailor_cannot_read_a_colleagues_rate`.
Everything else here is ordinary CRUD cover; that one is the reason the model was
put in its own table instead of onto Tailor, and it is the assertion that will
fail if a later phase ever publishes these columns through the roster.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from crm_api.models import Tailor

from .models import StaffProfile


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
