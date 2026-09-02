"""Phase 8: who a request is, and what an unknown answer is worth.

The question this module exists for is `test_deleting_a_staff_row_does_not
_promote_its_token`. Everything else is the matrix around it.

Until Phase 8 `resolve_user_role` answered OWNER for an account no profile
claimed, so the absence of a relationship was read as proof of ownership. The
absences were reachable from the product's own screens -- deleting a roster row
detached its User (Tailor.user is SET_NULL), and repointing an account's email
moved it -- which made dismissing a staff member the act that handed them the
boutique. These tests pin the inverse: an unrecognised account gets nothing,
and the owner is recognised positively, from the tenant's own owner_email.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.staff.models import StaffProfile
from core.roles import DESIGNER, OWNER, resolve_user_role
from crm_api.models import Tailor
from tenants.models import BoutiqueTenant, Domain

OWNER_EMAIL = 'owner@authz.test'


class AuthorizationTestCase(TenantTestCase):
    """One boutique, an owner recognised positively, and staff who are not."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = OWNER_EMAIL
        tenant.name = 'Authorization Atelier'
        return tenant

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        self.owner = User.objects.create_user(
            username=OWNER_EMAIL, email=OWNER_EMAIL, password='ownerpw12345')

        self.tailor_user = User.objects.create_user(
            username='rekha', email='rekha@authz.test', password='rekhapw12345')
        self.tailor = Tailor.objects.create(
            name='Rekha', specialty='Blouses', role='Tailor',
            email='rekha@authz.test', user=self.tailor_user)

        self.master_user = User.objects.create_user(
            username='vimala', email='vimala@authz.test', password='vimalapw12345')
        self.master = Tailor.objects.create(
            name='Vimala', specialty='Supervision', role='Master',
            email='vimala@authz.test', user=self.master_user)

        self.specialist_user = User.objects.create_user(
            username='arjun', email='arjun@authz.test', password='arjunpw12345')
        self.specialist = Tailor.objects.create(
            name='Arjun', specialty='Quality', role='QC Master',
            email='arjun@authz.test', user=self.specialist_user)

        for staff in (self.tailor, self.master, self.specialist):
            StaffProfile.objects.create(
                staff=staff, hourly_rate=Decimal('150.00'))

    def client_for(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Token {token.key}',
                        HTTP_X_TENANT_ID=self.tenant.schema_name)
        return api

    # The Owner-only financial surface, named individually. Protecting a parent
    # route is not protecting its actions, so every one is listed.
    def financial_urls(self):
        return [
            ('GET', reverse('payroll-period-list')),
            ('POST', reverse('payroll-period-generate')),
            ('GET', reverse('payroll-record-list')),
            ('GET', reverse('payroll-deposit-list')),
            ('GET', reverse('payroll-advance-list')),
            ('POST', reverse('payroll-advance-list')),
            ('GET', reverse('staff-profile-list')),
            ('POST', reverse('staff-profile-list')),
            ('GET', reverse('staff-review-list')),
            ('POST', reverse('staff-review-list')),
        ]

    def call(self, api, method, url, payload=None):
        return getattr(api, method.lower())(url, payload or {}, format='json')


class RoleResolutionTests(AuthorizationTestCase):
    """What each kind of account resolves to."""

    def test_the_owner_is_recognised_without_any_staff_profile(self):
        """The legitimate owner has no roster row and must keep the boutique."""
        self.assertIsNone(getattr(self.owner, 'tailor_profile', None))
        self.assertEqual(resolve_user_role(self.owner), OWNER)

    def test_the_owner_is_recognised_case_insensitively(self):
        self.owner.email = OWNER_EMAIL.upper()
        self.owner.save(update_fields=['email'])
        self.assertEqual(resolve_user_role(self.owner), OWNER)

    def test_staff_resolve_to_the_role_on_their_profile(self):
        self.assertEqual(resolve_user_role(self.tailor_user), 'Tailor')
        self.assertEqual(resolve_user_role(self.master_user), 'Master')
        self.assertEqual(resolve_user_role(self.specialist_user), 'QC Master')

    def test_an_account_no_profile_claims_resolves_to_nothing(self):
        """The Phase 8 invariant. A missing profile is not proof of ownership."""
        stranger = User.objects.create_user(
            username='stranger', email='stranger@authz.test', password='pw12345678')
        self.assertIsNone(resolve_user_role(stranger))

    def test_anonymous_and_none_resolve_to_nothing(self):
        self.assertIsNone(resolve_user_role(None))

        class Anon:
            is_authenticated = False
        self.assertIsNone(resolve_user_role(Anon()))


class DeletedStaffTests(AuthorizationTestCase):
    """Dismissing somebody must not be the act that promotes them."""

    def test_deleting_a_staff_row_does_not_promote_its_token(self):
        """The Phase 8 headline.

        Tailor.user is SET_NULL, so removing the roster row detaches the
        account and leaves it claimed by no profile. That used to resolve to
        OWNER, and the person's existing token -- never revoked -- carried the
        promotion into every Owner-only endpoint on the next request.
        """
        api = self.client_for(self.tailor_user)
        self.assertEqual(
            api.get(reverse('payroll-period-list')).status_code, 403,
            'a serving tailor should already be refused payroll')

        self.client_for(self.owner).delete(
            reverse('tailor-detail', args=[self.tailor.id]))

        self.tailor_user.refresh_from_db()
        self.assertFalse(self.tailor_user.is_active,
                         'the login left behind must be revoked')
        self.assertIsNone(resolve_user_role(self.tailor_user))

        # The SAME token object, reused exactly as an ex-employee would.
        for method, url in self.financial_urls():
            response = self.call(api, method, url)
            self.assertIn(response.status_code, (401, 403),
                          f'{method} {url} opened to a deleted staff token '
                          f'({response.status_code})')

    def test_a_detached_account_that_is_still_active_is_refused(self):
        """Deactivation is defence in depth, not the fix.

        Detaching without going through the viewset -- a data migration, a
        shell, any path that does not deactivate -- must still not promote.
        """
        self.tailor.user = None
        self.tailor.save(update_fields=['user'])
        self.assertTrue(self.tailor_user.is_active)
        self.assertIsNone(resolve_user_role(self.tailor_user))

        api = self.client_for(self.tailor_user)
        for method, url in self.financial_urls():
            response = self.call(api, method, url)
            self.assertIn(response.status_code, (401, 403),
                          f'{method} {url} opened to a detached account')

    def test_deleting_a_staff_row_keeps_the_financial_record(self):
        """Authorization is fixed by revoking access, not by destroying records.

        Every Phase 4-7 record points at the roster with SET_NULL and carries a
        name snapshot beside it, precisely so a payroll run stays readable after
        the person has gone. Revoking their login must not disturb that.

        NOTE Phase 3's AttendanceSession is CASCADE and does NOT survive. That
        is pre-existing and is left alone here -- see the Phase 8 report; it is
        a data-retention question, not an authorization one, and changing it
        would be a Phase 3 behaviour change this phase has no business making.
        """
        from apps.payroll.models import StaffAdvance
        from apps.staff.models import StaffPerformanceReview

        advance = StaffAdvance.objects.create(
            staff=self.tailor, staff_name_snapshot='Rekha',
            amount=Decimal('1000.00'), issued_on=date(2026, 9, 1))
        review = StaffPerformanceReview.objects.create(
            staff=self.tailor, staff_name_snapshot='Rekha',
            role_snapshot='Tailor', period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30), productivity_rating=4)
        user_id = self.tailor_user.id

        self.client_for(self.owner).delete(
            reverse('tailor-detail', args=[self.tailor.id]))

        self.assertTrue(User.objects.filter(id=user_id).exists(),
                        'the User row carries the audit trail and must survive')
        advance.refresh_from_db()
        review.refresh_from_db()
        self.assertIsNone(advance.staff_id)
        self.assertEqual(advance.staff_name_snapshot, 'Rekha')
        self.assertEqual(advance.amount, Decimal('1000.00'))
        self.assertIsNone(review.staff_id)
        self.assertEqual(review.role_snapshot, 'Tailor')

    def test_a_staff_row_cannot_be_given_the_owners_address(self):
        """User.email is not unique, and the owner is identified by email.

        Putting the owner's address on a roster row copied it onto that row's
        own User, which then resolved as the boutique owner.
        """
        self.client_for(self.owner).patch(
            reverse('tailor-detail', args=[self.tailor.id]),
            {'email': OWNER_EMAIL}, format='json')

        self.tailor_user.refresh_from_db()
        self.assertNotEqual((self.tailor_user.email or '').lower(), OWNER_EMAIL)
        self.assertNotEqual(resolve_user_role(self.tailor_user), OWNER)


class RoleTransitionTests(AuthorizationTestCase):
    """A role change must take effect on the next request, with no grace period."""

    def test_promotion_and_demotion_take_effect_immediately(self):
        api = self.client_for(self.tailor_user)
        team = reverse('staff-performance')

        self.tailor.role = 'Master'
        self.tailor.save(update_fields=['role'])
        self.assertEqual(resolve_user_role(self.tailor_user), 'Master')
        self.assertEqual(
            len(api.get(team, {'start': '2026-09-01', 'end': '2026-09-30'}).data['results']),
            3, 'a Master supervises the floor')

        self.tailor.role = 'Tailor'
        self.tailor.save(update_fields=['role'])
        self.assertEqual(resolve_user_role(self.tailor_user), 'Tailor')
        self.assertEqual(
            len(api.get(team, {'start': '2026-09-01', 'end': '2026-09-30'}).data['results']),
            1, 'a demoted account must lose the floor on the very next request')

    def test_no_role_change_grants_the_financial_surface(self):
        for role in ('Master', 'Tailor', 'QC Master', 'Pressing Staff', 'Designer'):
            self.tailor.role = role
            self.tailor.save(update_fields=['role'])
            api = self.client_for(self.tailor_user)
            for url in (reverse('payroll-period-list'),
                        reverse('payroll-deposit-list')):
                self.assertEqual(api.get(url).status_code, 403,
                                 f'{role} reached {url}')


class AuthorizationMatrixTests(AuthorizationTestCase):
    """Every role against every financial route, evaluated one route at a time."""

    def test_the_owner_reaches_the_financial_surface(self):
        api = self.client_for(self.owner)
        for url in (reverse('payroll-period-list'),
                    reverse('payroll-record-list'),
                    reverse('payroll-deposit-list'),
                    reverse('payroll-advance-list')):
            self.assertEqual(api.get(url).status_code, 200, url)

    def test_a_master_is_refused_every_owner_only_route(self):
        """Supervising the floor grants nothing about what the floor is paid."""
        api = self.client_for(self.master_user)
        for url in (reverse('payroll-period-list'),
                    reverse('payroll-deposit-list')):
            self.assertEqual(api.get(url).status_code, 403, url)
        for method, url in (('POST', reverse('payroll-period-generate')),
                            ('POST', reverse('payroll-advance-list')),
                            ('POST', reverse('staff-review-list'))):
            self.assertEqual(self.call(api, method, url).status_code, 403, url)

    def test_staff_may_not_write_anywhere_on_the_financial_surface(self):
        for user in (self.tailor_user, self.master_user, self.specialist_user):
            api = self.client_for(user)
            for method, url in (('POST', reverse('payroll-period-generate')),
                                ('POST', reverse('payroll-advance-list')),
                                ('POST', reverse('staff-profile-list')),
                                ('POST', reverse('staff-review-list'))):
                self.assertEqual(self.call(api, method, url).status_code, 403,
                                 f'{user.username} wrote {url}')

    def test_an_anonymous_caller_reaches_nothing(self):
        api = APIClient()
        api.credentials(HTTP_X_TENANT_ID=self.tenant.schema_name)
        for method, url in self.financial_urls():
            response = self.call(api, method, url)
            self.assertIn(response.status_code, (401, 403), f'{method} {url}')

    def test_an_invalid_token_reaches_nothing(self):
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION='Token deadbeefdeadbeefdeadbeef',
                        HTTP_X_TENANT_ID=self.tenant.schema_name)
        for method, url in self.financial_urls():
            self.assertIn(self.call(api, method, url).status_code, (401, 403))


class QuerysetScopeTests(AuthorizationTestCase):
    """A colleague's row must not be loaded and then hidden."""

    def test_staff_cannot_widen_their_scope_with_a_staff_parameter(self):
        for user, own in ((self.tailor_user, 'Rekha'),
                          (self.specialist_user, 'Arjun')):
            api = self.client_for(user)
            response = api.get(reverse('staff-performance'), {
                'start': '2026-09-01', 'end': '2026-09-30',
                'staff': self.master.id})
            names = [r['staff_name'] for r in response.data['results']]
            self.assertEqual(names, [own],
                             f'{user.username} widened scope with ?staff=')

    def test_a_colleagues_profile_is_not_readable_by_id(self):
        others = StaffProfile.objects.get(staff=self.master)
        api = self.client_for(self.tailor_user)
        response = api.get(reverse('staff-profile-detail', args=[others.id]))
        self.assertIn(response.status_code, (403, 404))
        self.assertNotIn(b'150.00', response.content)

    def test_a_master_sees_the_roster_without_its_pay(self):
        """Supervising a floor means knowing who is on it, not what it earns."""
        api = self.client_for(self.master_user)
        response = api.get(reverse('staff-profile-list'))
        self.assertEqual(response.status_code, 200)
        seen = {row['staff_name']: row for row in response.data}
        for name in ('Rekha', 'Arjun'):
            self.assertIn(name, seen, 'a Master supervises the floor')
            self.assertNotIn('hourly_rate', seen[name],
                             'and must not see what it is paid')
        # Their own row is self-service and keeps its terms.
        self.assertIn('hourly_rate', seen['Vimala'])

    #: Values a probe would actually send at an id-shaped parameter.
    JUNK = ('abc', '1 OR 1=1', '../../etc/passwd', '9' * 40, '', '%00',
            "1'; DROP TABLE staff_staffprofile;--", 'null', '-1', '1.5')

    def test_a_malformed_parameter_is_a_4xx_not_a_500(self):
        """A security probe must not reach a traceback (spec section 15).

        Every one of these went straight into the ORM, where a non-numeric id
        raises ValueError out of IntegerField, a non-UUID raises out of
        UUIDField and an impossible date raises out of parse_date -- none of
        which DRF converts.
        """
        api = self.client_for(self.owner)
        for url in (reverse('staff-performance'),
                    reverse('staff-attendance-list'),
                    reverse('staff-timesheet'),
                    reverse('payroll-record-list'),
                    reverse('payroll-advance-list')):
            for value in self.JUNK:
                response = api.get(url, {'staff': value,
                                         'start': '2026-09-01',
                                         'end': '2026-09-30'})
                self.assertLess(response.status_code, 500,
                                f'{url}?staff={value!r} returned '
                                f'{response.status_code}')

    def test_a_malformed_date_or_period_is_a_4xx_not_a_500(self):
        api = self.client_for(self.owner)
        for value in ('abc', '2026-02-30', '2026-13-01', '', '0000-00-00'):
            self.assertLess(
                api.get(reverse('staff-attendance-list'),
                        {'date': value}).status_code, 500, f'?date={value!r}')
            self.assertLess(
                api.get(reverse('staff-timesheet'),
                        {'week': value}).status_code, 500, f'?week={value!r}')
            self.assertLess(
                api.get(reverse('staff-review-list'),
                        {'since': value, 'until': value}).status_code, 500,
                f'?since={value!r}')
            self.assertLess(
                api.get(reverse('payroll-record-list'),
                        {'period': value}).status_code, 500, f'?period={value!r}')
            self.assertLess(
                api.get(reverse('staff-performance'),
                        {'start': value, 'end': value}).status_code, 500,
                f'?start={value!r}')


class CrossTenantAuthorizationTests(TransactionTestCase):
    """Two real schemas whose staff share a primary key.

    The adversarial setup the phase asks for: tenant A and tenant B each have a
    staff member with id 1, so a numeric id that is valid in one is valid in the
    other. A token from A must resolve nothing in B.
    """

    def _boutique(self, schema, email, name):
        tenant = BoutiqueTenant(schema_name=schema, owner_email=email, name=name)
        tenant.save()
        Domain.objects.get_or_create(
            domain=f'{schema}.localhost', tenant=tenant,
            defaults={'is_primary': True})
        return tenant

    def setUp(self):
        connection.set_schema_to_public()
        self.alpha = self._boutique('authz_alpha', 'owner@aa.test', 'Alpha')
        self.beta = self._boutique('authz_beta', 'owner@bb.test', 'Beta')
        self.tokens = {}
        for schema, email, staff_name in (
                ('authz_alpha', 'owner@aa.test', 'Alpha Worker'),
                ('authz_beta', 'owner@bb.test', 'Beta Worker')):
            with schema_context(schema):
                owner = User.objects.create_user(
                    username=email, email=email, password='ownerpw12345')
                staff = Tailor.objects.create(
                    name=staff_name, specialty='Stitching', role='Tailor')
                StaffProfile.objects.create(
                    staff=staff, hourly_rate=Decimal('150.00'))
                self.tokens[schema] = (
                    Token.objects.create(user=owner).key, staff.id)
        connection.set_schema_to_public()

    def tearDown(self):
        connection.set_schema_to_public()
        for schema in ('authz_alpha', 'authz_beta'):
            with connection.cursor() as c:
                c.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        BoutiqueTenant.objects.filter(
            schema_name__in=['authz_alpha', 'authz_beta']).delete()

    def client_for(self, schema, token=None):
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Token {token or self.tokens[schema][0]}',
                        HTTP_X_TENANT_ID=schema)
        return api

    def test_both_boutiques_really_do_share_a_staff_id(self):
        """The premise of every test below, asserted so it cannot rot."""
        self.assertEqual(self.tokens['authz_alpha'][1],
                         self.tokens['authz_beta'][1])

    def test_a_token_from_one_boutique_is_not_a_token_in_the_other(self):
        alpha_token = self.tokens['authz_alpha'][0]
        api = self.client_for('authz_beta', token=alpha_token)
        for url in (reverse('staff-profile-list'),
                    reverse('payroll-period-list'),
                    reverse('payroll-deposit-list'),
                    reverse('payroll-advance-list'),
                    reverse('staff-review-list')):
            response = api.get(url)
            self.assertIn(response.status_code, (401, 403),
                          f'{url} accepted the other boutique\'s token')

    def test_a_shared_staff_id_resolves_only_inside_its_own_boutique(self):
        staff_id = self.tokens['authz_alpha'][1]
        api = self.client_for('authz_alpha')
        response = api.get(reverse('staff-performance'), {
            'start': '2026-09-01', 'end': '2026-09-30', 'staff': staff_id})
        names = [r['staff_name'] for r in response.data['results']]
        self.assertEqual(names, ['Alpha Worker'])
        self.assertNotIn('Beta Worker', response.content.decode())

    def test_a_tenant_header_naming_another_boutique_is_refused(self):
        """Alpha's token must never be admitted to Beta by asking."""
        alpha_token = self.tokens['authz_alpha'][0]
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Token {alpha_token}',
                        HTTP_X_TENANT_ID='authz_beta')
        self.assertIn(api.get(reverse('payroll-period-list')).status_code,
                      (401, 403))

    def test_a_malformed_tenant_header_is_a_controlled_answer(self):
        """Never a 500, and never somebody else's boutique.

        'public' is NOT an error here: the middleware skips it deliberately and
        falls through to resolving the tenant from the token, so the caller
        lands in their OWN boutique. That is the safe outcome, and what matters
        is that no header value reaches a different one -- which is what this
        asserts, rather than asserting a status code that legitimately varies.
        """
        alpha_token = self.tokens['authz_alpha'][0]
        for header in ('no_such_schema', '', 'public',
                       'public; DROP SCHEMA x', '../../etc', 'PUBLIC'):
            api = APIClient()
            api.credentials(HTTP_AUTHORIZATION=f'Token {alpha_token}',
                            HTTP_X_TENANT_ID=header)
            response = api.get(reverse('staff-profile-list'))
            self.assertLess(response.status_code, 500,
                            f'X-Tenant-ID {header!r} returned '
                            f'{response.status_code}')
            body = response.content.decode()
            for secret in ('Beta Worker', 'owner@bb.test', 'authz_beta'):
                self.assertNotIn(secret, body,
                                 f'X-Tenant-ID {header!r} leaked {secret!r}')

    def test_an_error_body_never_names_the_other_boutique(self):
        alpha_token = self.tokens['authz_alpha'][0]
        api = self.client_for('authz_beta', token=alpha_token)
        for url in (reverse('staff-profile-list'),
                    reverse('payroll-record-list')):
            body = api.get(url).content.decode()
            for secret in ('Beta Worker', 'owner@bb.test', 'authz_beta', '150.00'):
                self.assertNotIn(secret, body,
                                 f'{url} leaked {secret!r} across tenants')


class ConfidentialFieldTests(AuthorizationTestCase):
    """Money must be absent from the payload, not merely hidden by the interface."""

    #: Every field that would tell a colleague what somebody earns or owes.
    MONEY = ('hourly_rate', 'weekly_hours', 'deposit_total', 'deposit_weekly',
             'gross_earnings', 'net_payable', 'payout', 'advance_amount')

    def test_a_colleagues_money_never_reaches_a_non_owner(self):
        """Reading your OWN terms is self-service; reading a colleague's is not.

        Checked row by row rather than over the whole body, because the caller's
        own row legitimately carries their rate and a body-wide assertion would
        pass or fail for the wrong reason.
        """
        for user, own in ((self.tailor_user, self.tailor),
                          (self.master_user, self.master),
                          (self.specialist_user, self.specialist)):
            api = self.client_for(user)
            response = api.get(reverse('staff-profile-list'))
            self.assertEqual(response.status_code, 200)
            for row in response.data:
                if row['staff'] == own.id:
                    continue
                for field in self.MONEY:
                    self.assertNotIn(
                        field, row,
                        f"{user.username} read {field} off {row['staff_name']}")

    def test_no_money_appears_on_the_operational_routes_at_all(self):
        for user in (self.tailor_user, self.master_user, self.specialist_user):
            api = self.client_for(user)
            for url in (reverse('staff-attendance-list'),
                        reverse('staff-performance'),
                        reverse('staff-review-list')):
                response = api.get(url, {'start': '2026-09-01',
                                         'end': '2026-09-30'})
                if response.status_code != 200:
                    continue
                body = response.content.decode()
                for field in self.MONEY:
                    self.assertNotIn(field, body,
                                     f'{user.username} saw {field} at {url}')
                self.assertNotIn('150.00', body,
                                 f'{user.username} saw a rate at {url}')

    def test_the_activity_feed_carries_no_money_to_a_supervisor(self):
        from apps.activities.models import UniversalActivity
        UniversalActivity.objects.create(
            user=self.owner, user_name_snapshot='Owner', module='payroll',
            entity_type='PayrollRecord', entity_id='1', action='PAYROLL_APPROVED',
            title='Payroll approved', description='')
        api = self.client_for(self.master_user)
        response = api.get('/api/activities/')
        if response.status_code == 200:
            body = response.content.decode()
            for field in self.MONEY:
                self.assertNotIn(field, body)


class DeletionRaceTests(TransactionTestCase):
    """Deleting a profile while a privileged call is in flight (spec section 23)."""

    def setUp(self):
        connection.set_schema_to_public()
        self.tenant = BoutiqueTenant(
            schema_name='authz_race', owner_email='owner@race.test', name='Race')
        self.tenant.save()
        Domain.objects.get_or_create(
            domain='authz_race.localhost', tenant=self.tenant,
            defaults={'is_primary': True})
        with schema_context('authz_race'):
            self.staff_user = User.objects.create_user(
                username='racer', email='racer@race.test', password='racerpw12345')
            self.staff = Tailor.objects.create(
                name='Racer', specialty='Stitching', role='Tailor',
                email='racer@race.test', user=self.staff_user)
            StaffProfile.objects.create(staff=self.staff)
            self.token = Token.objects.create(user=self.staff_user).key
        connection.set_schema_to_public()

    def tearDown(self):
        connection.set_schema_to_public()
        with connection.cursor() as c:
            c.execute('DROP SCHEMA IF EXISTS "authz_race" CASCADE')
        BoutiqueTenant.objects.filter(schema_name='authz_race').delete()

    def test_deleting_the_profile_never_leaves_the_token_privileged(self):
        """Whichever way the race lands, the outcome must be refusal.

        Both interleavings are checked from one direction, because there is no
        ordering in which "profile gone" should mean "more access": before the
        delete the account is a Tailor and refused, after it the account is
        unknown and refused.
        """
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Token {self.token}',
                        HTTP_X_TENANT_ID='authz_race')
        url = reverse('payroll-period-list')

        self.assertEqual(api.get(url).status_code, 403)
        with schema_context('authz_race'):
            Tailor.objects.filter(pk=self.staff.pk).delete()
        self.assertIn(api.get(url).status_code, (401, 403))


class RehireAndDualRoleTests(AuthorizationTestCase):
    """What deactivate-on-delete must not break (Phase 8 review findings)."""

    def test_rehiring_a_deleted_staff_member_issues_a_working_login(self):
        """Deactivate-on-delete needs an undo the owner can actually reach.

        Deleting revoked the login; re-adding the same person then relinked the
        DEAD account and printed no password, so the roster looked healthy while
        the account could never be signed into -- and password reset answers the
        same generic 200 for an inactive user as for an unknown address, so
        there was no way out inside the product.
        """
        owner_api = self.client_for(self.owner)
        owner_api.delete(reverse('tailor-detail', args=[self.tailor.id]))
        self.tailor_user.refresh_from_db()
        self.assertFalse(self.tailor_user.is_active)

        response = owner_api.post(reverse('tailor-list'), {
            'name': 'Rekha', 'specialty': 'Blouses', 'role': 'Tailor',
            'email': 'rekha@authz.test'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIn('bootstrap_password', response.data,
                      'a re-hire must come with a credential to hand over')

        self.tailor_user.refresh_from_db()
        self.assertTrue(self.tailor_user.is_active)
        self.assertTrue(self.tailor_user.check_password(
            response.data['bootstrap_password']))

    def test_a_rehire_does_not_revive_the_old_token(self):
        """Coming back must not restore the credential they left with."""
        old = Token.objects.create(user=self.tailor_user).key
        owner_api = self.client_for(self.owner)
        owner_api.delete(reverse('tailor-detail', args=[self.tailor.id]))
        owner_api.post(reverse('tailor-list'), {
            'name': 'Rekha', 'specialty': 'Blouses', 'role': 'Tailor',
            'email': 'rekha@authz.test'}, format='json')

        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Token {old}',
                        HTTP_X_TENANT_ID=self.tenant.schema_name)
        self.assertIn(api.get(reverse('payroll-period-list')).status_code,
                      (401, 403))
        self.assertFalse(Token.objects.filter(key=old).exists())

    def test_deleting_one_profile_leaves_a_dual_role_account_alive(self):
        """One person, two jobs. Losing one must not close the account."""
        from apps.design_studio.models import Designer
        Designer.objects.create(name='Rekha', email='rekha@authz.test',
                                user=self.tailor_user)

        self.client_for(self.owner).delete(
            reverse('tailor-detail', args=[self.tailor.id]))

        self.tailor_user.refresh_from_db()
        self.assertTrue(self.tailor_user.is_active,
                        'she is still a designer here')
        self.assertEqual(resolve_user_role(self.tailor_user), DESIGNER)

    def test_a_second_roster_row_on_a_taken_address_does_not_500(self):
        """Tailor.user is a OneToOne; linking a claimed account raised
        IntegrityError after the row had already been committed."""
        response = self.client_for(self.owner).post(reverse('tailor-list'), {
            'name': 'Someone Else', 'specialty': 'Blouses', 'role': 'Tailor',
            'email': 'rekha@authz.test'}, format='json')
        self.assertLess(response.status_code, 500, response.data)
        self.tailor.refresh_from_db()
        self.assertEqual(self.tailor.user_id, self.tailor_user.id,
                         "the original owner of the address keeps it")

    def test_the_owners_account_is_never_renamed_off_the_owner_address(self):
        """A legacy boutique can have the owner's User on a roster row."""
        legacy = Tailor.objects.create(
            name='Boss', specialty='All', role='Master',
            email=OWNER_EMAIL, user=self.owner)
        self.client_for(self.owner).patch(
            reverse('tailor-detail', args=[legacy.id]),
            {'email': 'somethingelse@authz.test'}, format='json')
        self.owner.refresh_from_db()
        self.assertEqual((self.owner.email or '').lower(), OWNER_EMAIL)
        self.assertEqual(resolve_user_role(self.owner), OWNER)


class PerformerAttributionTests(AuthorizationTestCase):
    """Signing somebody else's name to the work is a supervisor's call."""

    def test_a_tailor_cannot_name_a_colleague_as_the_performer(self):
        from crm_api.models import Customer, Order, OrderStage
        customer = Customer.objects.create(
            first_name='Perf', last_name='Client', mobile_number='9600000902')
        order = Order.objects.create(order_id='T2B-AUTHZ-1', customer=customer,
                                     tailor=self.tailor)
        stage = OrderStage.objects.create(
            order=order, stage_key='stitching_in_progress',
            stage_name='Stitching', status='NOT_STARTED',
            assigned_to=self.tailor)

        response = self.client_for(self.tailor_user).post(
            reverse('order-transition-stage', args=[order.id]),
            {'stage_key': 'stitching_in_progress', 'status': 'IN_PROGRESS',
             'performed_by_id': self.master.id}, format='json')
        self.assertLess(response.status_code, 500, getattr(response, 'data', ''))

        stage.refresh_from_db()
        self.assertNotEqual(stage.performed_by_id, self.master.id,
                            'a tailor signed a colleague to the work')

    def test_a_malformed_performer_id_is_not_a_server_error(self):
        from crm_api.models import Customer, Order, OrderStage
        customer = Customer.objects.create(
            first_name='Perf2', last_name='Client', mobile_number='9600000903')
        order = Order.objects.create(order_id='T2B-AUTHZ-2', customer=customer)
        OrderStage.objects.create(
            order=order, stage_key='stitching_in_progress',
            stage_name='Stitching', status='NOT_STARTED')

        for junk in ('abc', {}, [], '1.5'):
            response = self.client_for(self.owner).post(
                reverse('order-transition-stage', args=[order.id]),
                {'stage_key': 'stitching_in_progress', 'status': 'IN_PROGRESS',
                 'performed_by_id': junk}, format='json')
            self.assertLess(response.status_code, 500,
                            f'performed_by_id={junk!r}')
