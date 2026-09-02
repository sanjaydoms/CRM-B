"""Reading and acting on accounts that live in fifty different schemas.

Two failure modes are worth more than the rest of this file put together, and
both of them are quiet:

  * A role resolved in the wrong context. Nothing crashes -- the console just
    labels the boutique owner as staff, or a staff member as the owner, and an
    administrator acts on that label.
  * A merge that leaks. Filtering by one boutique and getting rows from another
    is the single thing a multi-tenant console must never do, and it looks
    exactly like a working screen.

The tenants here are real Postgres schemas built and dropped per test (see
temporary_tenant in superadmin/tests.py), because a mocked schema switch would
test nothing at all: the switch is the behaviour under test.
"""

from contextlib import contextmanager

from django.contrib.auth.models import User
from django.core import mail
from django.db import connection, transaction
from django.test import TransactionTestCase
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from crm_api.models import Customer, Order, Tailor
from superadmin.models import AuditLog, ErrorEvent
from superadmin.schemas import MissingSchema, forget
from superadmin.search import DEFAULT_PER_TYPE, search
from superadmin.serializers import TenantSerializer
from superadmin.tests import temporary_tenant
from superadmin.users import (DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, clamped_int, issue_access_link,
                              list_users, revoke_sessions, set_user_active,
                              trigger_password_reset)
# The console client helper lives with the console's own tests; imported
# rather than re-declared so both files sign in the same way.
from superadmin.tests import admin_client
from tenants.middleware import clear_tenant_cache
from tenants.models import BoutiqueTenant


def boutiques():
    """The tenant list the console hands in -- superadmin.views._boutiques()."""
    connection.set_schema_to_public()
    return list(BoutiqueTenant.objects.exclude(schema_name='public'))


@contextmanager
def ghost_tenant(schema_name, owner_email, name, empty_schema=False):
    """A boutique the registry knows about and the database does not.

    Not an exotic state: a restored dump, an interrupted signup, a hand-written
    row or `delete(force_drop=False)` all produce one, and this is what
    superadmin/schemas.py was written to survive.

    Built the way django_tenants itself provides for -- TenantMixin.save() reads
    `auto_create_schema` off the instance, so clearing it there leaves the row
    with no schema. Creating the tenant and then dropping the schema by hand
    would work too, but it would also poison schemas._present with a positive
    result for a schema that is now gone.

    `empty_schema=True` gives the OTHER half of the same failure: a schema that
    exists but holds no tables (a half-run migration). It is the more dangerous
    of the two to test with, because the existence check passes and the query
    itself fails against the database -- which is what the savepoint in
    for_each_tenant is for.
    """
    connection.set_schema_to_public()
    tenant = BoutiqueTenant(schema_name=schema_name, owner_email=owner_email,
                            name=name)
    tenant.auto_create_schema = False
    tenant.save()
    if empty_schema:
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA "{schema_name}"')
    try:
        yield tenant
    finally:
        connection.set_schema_to_public()
        if empty_schema:
            with connection.cursor() as cursor:
                cursor.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
            # The presence cache holds positive answers for the life of the
            # process, so a schema dropped behind its back has to be named.
            forget(schema_name)
        tenant.delete(force_drop=False)


class PlatformUserListTests(TransactionTestCase):

    def setUp(self):
        connection.set_schema_to_public()

    def test_users_from_two_boutiques_are_listed_and_attributed(self):
        with temporary_tenant('sa_us_a', 'owner@usa.test', 'Atelier A'), \
                temporary_tenant('sa_us_b', 'owner@usb.test', 'Atelier B'):
            with schema_context('sa_us_a'):
                User.objects.create_user(username='owner@usa.test',
                                         email='owner@usa.test', password='pw')
                cutter = User.objects.create_user(username='cutter@usa.test',
                                                  email='cutter@usa.test')
                Tailor.objects.create(name='Cutter', specialty='Cutting',
                                      role='Cutting Master', user=cutter)
            with schema_context('sa_us_b'):
                User.objects.create_user(username='owner@usb.test',
                                         email='owner@usb.test')

            body = list_users(boutiques())
            rows = {(r['boutique'], r['username']): r for r in body['users']}

            self.assertEqual(body['count'], 3)
            self.assertEqual(
                rows[('sa_us_a', 'owner@usa.test')]['role'], 'Owner')
            # Reported by their production role, not flattened to "staff".
            self.assertEqual(
                rows[('sa_us_a', 'cutter@usa.test')]['role'], 'Cutting Master')
            self.assertEqual(
                rows[('sa_us_b', 'owner@usb.test')]['role'], 'Owner')
            # Each row says which boutique it came from, by schema and by name.
            self.assertEqual(
                rows[('sa_us_b', 'owner@usb.test')]['boutique_name'], 'Atelier B')

    def test_an_owner_who_also_works_the_floor_is_still_the_owner(self):
        """The one that tenant_context buys and schema_context does not.

        schema_context binds a FakeTenant with no owner_email, so
        resolve_user_role's positive owner check never fires and this account --
        which has a Tailor profile -- comes back as 'Master'. Login and
        /auth/me call the same person Owner, and a console that disagrees with
        the product about who owns a boutique is worse than no console.
        """
        with temporary_tenant('sa_us_floor', 'owner@floor.test', 'Floor Atelier'):
            with schema_context('sa_us_floor'):
                owner = User.objects.create_user(username='owner@floor.test',
                                                 email='owner@floor.test')
                Tailor.objects.create(name='Owner', specialty='All',
                                      role='Master', user=owner)

            row = list_users(boutiques(), boutique='sa_us_floor')['users'][0]
            self.assertEqual(row['role'], 'Owner')
            # Still reported as having the profile -- the role is the question,
            # not whether the profile exists.
            self.assertIsNotNone(row['tailor_id'])

    def test_filtering_by_boutique_does_not_leak_the_other(self):
        with temporary_tenant('sa_us_one', 'owner@one.test', 'One'), \
                temporary_tenant('sa_us_two', 'owner@two.test', 'Two'):
            with schema_context('sa_us_one'):
                User.objects.create_user(username='only@one.test')
            with schema_context('sa_us_two'):
                User.objects.create_user(username='only@two.test')

            body = list_users(boutiques(), boutique='sa_us_one')
            self.assertEqual({r['boutique'] for r in body['users']}, {'sa_us_one'})
            self.assertEqual(body['count'], 1)
            self.assertNotIn('only@two.test', str(body))

    def test_search_and_role_filters_narrow_the_merged_list(self):
        with temporary_tenant('sa_us_f', 'owner@f.test', 'Filterable'):
            with schema_context('sa_us_f'):
                stitcher = User.objects.create_user(username='stitcher@f.test',
                                                    first_name='Nadia')
                Tailor.objects.create(name='Nadia', specialty='Stitching',
                                      role='Tailor', user=stitcher)
                User.objects.create_user(username='owner@f.test',
                                         email='owner@f.test')

            tenants = boutiques()
            self.assertEqual(
                [r['username'] for r in list_users(tenants, search='Nadia')['users']],
                ['stitcher@f.test'])
            self.assertEqual(
                [r['username'] for r in list_users(tenants, role='Owner')['users']],
                ['owner@f.test'])

    def test_last_login_is_reported_as_untracked_rather_than_never(self):
        """login() is never called in this product, so the column is NULL for
        everyone. The field is present and the envelope says why."""
        with temporary_tenant('sa_us_ll', 'owner@ll.test', 'Login Atelier'):
            with schema_context('sa_us_ll'):
                User.objects.create_user(username='owner@ll.test')

            body = list_users(boutiques(), boutique='sa_us_ll')
            self.assertIn('last_login', body['users'][0])
            self.assertIsNone(body['users'][0]['last_login'])
            self.assertIs(body['last_login_tracked'], False)


class UserActionTests(TransactionTestCase):

    def setUp(self):
        connection.set_schema_to_public()

    def test_the_owner_cannot_be_deactivated(self):
        """An owner switched off here has no route back in: every screen that
        could undo it is refused to them, and reset skips inactive users."""
        with temporary_tenant('sa_ua_own', 'owner@own.test', 'Owned'):
            with schema_context('sa_ua_own'):
                User.objects.create_user(username='owner@own.test',
                                         email='owner@own.test')

            ok, message = set_user_active('sa_ua_own', 'owner@own.test', False)
            self.assertFalse(ok)
            self.assertIn('owner', message.lower())

            with schema_context('sa_ua_own'):
                self.assertTrue(
                    User.objects.get(username='owner@own.test').is_active)

    def test_staff_are_deactivated_and_reactivated(self):
        with temporary_tenant('sa_ua_staff', 'owner@st.test', 'Staffed'):
            with schema_context('sa_ua_staff'):
                User.objects.create_user(username='helper@st.test',
                                         email='helper@st.test')

            ok, _ = set_user_active('sa_ua_staff', 'helper@st.test', False)
            self.assertTrue(ok)
            with schema_context('sa_ua_staff'):
                self.assertFalse(
                    User.objects.get(username='helper@st.test').is_active)

            ok, _ = set_user_active('sa_ua_staff', 'helper@st.test', True)
            self.assertTrue(ok)
            with schema_context('sa_ua_staff'):
                self.assertTrue(
                    User.objects.get(username='helper@st.test').is_active)

    def test_an_unknown_boutique_or_user_is_refused_not_guessed(self):
        with temporary_tenant('sa_ua_404', 'owner@404.test', 'Missing'):
            self.assertEqual(
                set_user_active('no_such_schema', 'anyone', False)[0], False)
            self.assertEqual(
                set_user_active('sa_ua_404', 'nobody@404.test', False)[0], False)
            self.assertEqual(
                revoke_sessions('sa_ua_404', 'nobody@404.test')[0], False)

    def test_revoking_sessions_deletes_the_token_and_the_api_refuses(self):
        """The only real sign-out this product has: DRF tokens never expire."""
        with temporary_tenant('sa_ua_tok', 'owner@tok3.test', 'Token Atelier'):
            with schema_context('sa_ua_tok'):
                # Given the boutique's owner_email so the API answers at all:
                # this test is about revoking a token, and it needs a call that
                # succeeds BEFORE the revocation to have anything to prove.
                # A profile-less account stopped being the owner in Phase 8.
                staff = User.objects.create_user(
                    username='staff@tok3.test', email='owner@tok3.test')
                token, _ = Token.objects.get_or_create(user=staff)
                key = token.key

            def call_api():
                client = APIClient()
                client.credentials(HTTP_AUTHORIZATION='Token ' + key,
                                   HTTP_X_TENANT_ID='sa_ua_tok')
                return client.get('/api/customers/').status_code

            self.assertEqual(call_api(), 200)

            before = list_users(boutiques(), boutique='sa_ua_tok')
            self.assertIs(before['users'][0]['has_token'], True)
            # Whether a token exists, never which one it is.
            self.assertNotIn(key, str(before))

            ok, _ = revoke_sessions('sa_ua_tok', 'staff@tok3.test')
            self.assertTrue(ok)
            self.assertEqual(call_api(), 401)

            after = list_users(boutiques(), boutique='sa_ua_tok')
            self.assertIs(after['users'][0]['has_token'], False)
            # The account still exists and can sign in again -- revoking a
            # session is not locking an account.
            self.assertIs(after['users'][0]['is_active'], True)

            # Nothing left to revoke is the state that was asked for, not an
            # error the administrator has to interpret.
            self.assertTrue(revoke_sessions('sa_ua_tok', 'staff@tok3.test')[0])

    def test_password_reset_goes_through_the_boutiques_own_flow(self):
        with temporary_tenant('sa_ua_pw', 'owner@pw2.test', 'Reset Atelier'):
            with schema_context('sa_ua_pw'):
                User.objects.create_user(username='owner@pw2.test',
                                         email='owner@pw2.test')
            mail.outbox = []

            ok, message = trigger_password_reset('sa_ua_pw', 'owner@pw2.test')
            self.assertTrue(ok, message)
            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].to, ['owner@pw2.test'])
            # The link the product itself sends: schema-carrying payload,
            # composed by PasswordResetRequestView rather than here.
            self.assertIn('?reset=sa_ua_pw.', mail.outbox[0].body)
            self.assertIn('Reset Atelier', mail.outbox[0].subject)

    def test_password_reset_refuses_a_deactivated_account(self):
        """PasswordResetRequestView drops inactive users silently, which is the
        right answer to a stranger and the wrong one to an administrator."""
        with temporary_tenant('sa_ua_pw2', 'owner@pw3.test', 'Quiet Atelier'):
            with schema_context('sa_ua_pw2'):
                User.objects.create_user(username='gone@pw3.test',
                                         email='gone@pw3.test', is_active=False)
            mail.outbox = []

            ok, message = trigger_password_reset('sa_ua_pw2', 'gone@pw3.test')
            self.assertFalse(ok)
            self.assertIn('deactivated', message.lower())
            self.assertEqual(mail.outbox, [])


class GlobalSearchTests(TransactionTestCase):

    def setUp(self):
        connection.set_schema_to_public()

    def test_a_customer_is_found_in_their_own_boutique_and_nowhere_else(self):
        with temporary_tenant('sa_se_a', 'owner@sea.test', 'Atelier Sea'), \
                temporary_tenant('sa_se_b', 'owner@seb.test', 'Atelier Seb'):
            with schema_context('sa_se_a'):
                customer = Customer.objects.create(first_name='Zerlina',
                                                   last_name='Quill',
                                                   mobile_number='9000007001')
                Order.objects.create(order_id='SE-1', customer=customer,
                                     total_amount=900, order_status='Received')
            with schema_context('sa_se_b'):
                Customer.objects.create(first_name='Someone', last_name='Else',
                                        mobile_number='9000007002')

            hits = search('Zerlina', boutiques())
            customers = [h for h in hits if h['type'] == 'customer']
            self.assertEqual(len(customers), 1)
            self.assertEqual(customers[0]['label'], 'Zerlina Quill')
            self.assertEqual(customers[0]['boutique'], 'sa_se_a')
            self.assertEqual(customers[0]['boutique_name'], 'Atelier Sea')

            # The order is found by the customer's name too -- a support call
            # names a person far more often than an order id.
            orders = [h for h in hits if h['type'] == 'order']
            self.assertEqual([o['id'] for o in orders], ['SE-1'])
            self.assertEqual(orders[0]['boutique'], 'sa_se_a')

            # Every key in a mixed list is distinct, so the console can render
            # it without two rows colliding on a primary key from two schemas.
            self.assertEqual(len({h['key'] for h in hits}), len(hits))

            # Asked about the other boutique only, that customer does not exist.
            only_b = [t for t in boutiques() if t.schema_name == 'sa_se_b']
            self.assertEqual(search('Zerlina', only_b), [])

    def test_a_boutique_and_a_user_are_found_by_their_own_columns(self):
        with temporary_tenant('sa_se_named', 'owner@named.test', 'Marigold House'):
            with schema_context('sa_se_named'):
                User.objects.create_user(username='hana@named.test',
                                         first_name='Hana', last_name='Rao')

            tenants = boutiques()
            found = search('Marigold', tenants)
            self.assertEqual([h['type'] for h in found], ['boutique'])
            self.assertEqual(found[0]['id'], 'sa_se_named')

            users = [h for h in search('Hana', tenants) if h['type'] == 'user']
            self.assertEqual(len(users), 1)
            # The id is the username, which is what superadmin/users.py acts on.
            self.assertEqual(users[0]['id'], 'hana@named.test')
            self.assertEqual(users[0]['boutique'], 'sa_se_named')

    def test_the_consoles_own_tables_are_searchable(self):
        """Errors and audit entries are the two types with no schema of their
        own, and both carry a schema *name* rather than a foreign key. A typo in
        either branch takes the whole search box down, not just its section."""
        with temporary_tenant('sa_se_pub', 'owner@pub.test', 'Public Atelier'):
            AuditLog.objects.create(actor='platform@admin.test',
                                    action='boutique.suspend',
                                    target='sa_se_pub', boutique='sa_se_pub')
            ErrorEvent.objects.create(fingerprint='se-pub-1',
                                      exception_type='ZeroDivisionError',
                                      message='division by zero',
                                      path='/api/orders/', boutique='sa_se_pub')

            audit = [h for h in search('sa_se_pub', boutiques())
                     if h['type'] == 'audit']
            self.assertEqual(len(audit), 1)
            self.assertIn('Boutique suspended', audit[0]['label'])

            errors = [h for h in search('ZeroDivision', boutiques())
                      if h['type'] == 'error']
            self.assertEqual(len(errors), 1)
            self.assertEqual(errors[0]['boutique'], 'sa_se_pub')
            # The stored schema name is resolved to the boutique's own name from
            # the tenant list already in memory, not by a lookup per row.
            self.assertEqual(errors[0]['boutique_name'], 'Public Atelier')

    def test_a_one_character_term_scans_nothing(self):
        with temporary_tenant('sa_se_short', 'owner@short.test', 'Short'):
            with schema_context('sa_se_short'):
                Customer.objects.create(first_name='Z', last_name='Z',
                                        mobile_number='9000007003')

            tenants = boutiques()
            self.assertEqual(search('Z', tenants), [])
            self.assertEqual(search('', tenants), [])
            self.assertEqual(search(None, tenants), [])
            # Two characters is the floor, and it does search.
            self.assertTrue(search('Sh', tenants))

    def test_a_malformed_limit_is_the_default_not_a_500(self):
        with temporary_tenant('sa_se_junk', 'owner@junk.test', 'Junk Atelier'):
            with schema_context('sa_se_junk'):
                for i in range(DEFAULT_PER_TYPE + 3):
                    Customer.objects.create(first_name='Repeat',
                                            last_name=f'Number{i}',
                                            mobile_number=f'90000090{i:02d}')

            tenants = boutiques()

            def customers(limit):
                return [h for h in search('Repeat', tenants, limit_per_type=limit)
                        if h['type'] == 'customer']

            # Not a number at all -> the default, the same answer as no
            # parameter. Previously a ValueError, an HTTP 500 and an ErrorEvent.
            for junk in ('abc', '', None, '12abc', [], '3.7'):
                self.assertEqual(len(customers(junk)), DEFAULT_PER_TYPE, junk)
            # A number that is out of range is clamped, not refused: these are
            # bounds on the answer, not input validation the caller must pass.
            self.assertEqual(len(customers('-4')), 1)
            self.assertEqual(len(customers('9' * 40)), DEFAULT_PER_TYPE + 3)

    def test_per_type_cap_bounds_the_answer(self):
        with temporary_tenant('sa_se_cap', 'owner@cap.test', 'Capped'):
            with schema_context('sa_se_cap'):
                for i in range(8):
                    Customer.objects.create(first_name='Repeat',
                                            last_name=f'Number{i}',
                                            mobile_number=f'90000080{i:02d}')

            hits = search('Repeat', boutiques(), limit_per_type=3)
            self.assertEqual(len([h for h in hits if h['type'] == 'customer']), 3)


class GhostBoutiqueTests(TransactionTestCase):
    """A boutique with a registry row and no schema.

    Every assertion in this class PASSED WRONGLY before superadmin/schemas.py,
    and none of them raised anything for a try/except to catch. django_tenants
    selects a tenant with `SET search_path = 'the_schema', public` without
    checking the schema is there, Postgres skips a missing entry rather than
    failing, and `auth` is a SHARED_APP -- so auth_user really does exist at the
    next entry in the path. Reads returned the console's own superuser labelled
    as that boutique's staff, and the deactivation below turned OFF the account
    of the administrator who clicked it.

    The public superuser built in setUp is the tripwire: it is the row the
    fallthrough lands on, so any of these tests seeing it is that defect back.
    """

    def setUp(self):
        connection.set_schema_to_public()
        self.admin = User.objects.create_superuser(
            username='platform@ghost.test', email='platform@ghost.test',
            password='pw')
        self.token, _ = Token.objects.get_or_create(user=self.admin)

    def test_a_ghost_boutique_is_named_unreadable_and_yields_no_rows(self):
        with ghost_tenant('sa_gh_list', 'owner@gh1.test', 'Ghost Atelier'):
            body = list_users(boutiques(), boutique='sa_gh_list')

            self.assertEqual(body['unreadable'], ['sa_gh_list'])
            self.assertEqual(body['users'], [])
            self.assertEqual(body['count'], 0)
            # The specific wrong answer: the platform's own account, attributed
            # to a boutique it has nothing to do with.
            self.assertNotIn('platform@ghost.test', str(body))

    def test_search_does_not_attribute_the_platform_superuser_to_a_ghost(self):
        with ghost_tenant('sa_gh_find', 'owner@gh2.test', 'Ghost Two'):
            hits = search('platform@ghost.test', boutiques())
            self.assertEqual([h for h in hits if h['type'] == 'user'], [])

            # Nor by a term the console account matches loosely -- 'platform'
            # is what an administrator on a support call would actually type.
            hits = search('platform', boutiques())
            self.assertEqual([h for h in hits if h['type'] == 'user'], [])

        # The other half of the same fallthrough, and the one the existence
        # check cannot see: a schema that IS there and holds no tables. auth is
        # a SHARED_APP, so auth_user still resolves to public and _user_hits
        # answers with the console's own account; only the next query fails.
        # Anything gathered from a boutique that could not be read whole is
        # dropped, so no partial answer carries those rows out.
        with ghost_tenant('sa_gh_empty', 'owner@gh6.test', 'Empty Atelier',
                          empty_schema=True):
            hits = search('platform', boutiques())
            self.assertEqual([h for h in hits if h['type'] == 'user'], [])

    def test_a_write_to_a_ghost_boutique_never_reaches_the_public_account(self):
        """The critical one.

        set_user_active('a ghost', 'platform@ghost.test', False) used to resolve
        auth_user through to `public` and deactivate the console administrator's
        own login -- one click on a broken boutique disabling the account doing
        the clicking, with the console reporting success. A mutation lets
        MissingSchema propagate rather than continuing (superadmin/schemas.py):
        a write that cannot reach the right schema must not reach another one.
        """
        with ghost_tenant('sa_gh_write', 'owner@gh3.test', 'Ghost Three'):
            with self.assertRaises(MissingSchema):
                set_user_active('sa_gh_write', 'platform@ghost.test', False)

            # revoke_sessions is the same write against a different table: it
            # would have deleted the administrator's own authtoken row.
            with self.assertRaises(MissingSchema):
                revoke_sessions('sa_gh_write', 'platform@ghost.test')

            connection.set_schema_to_public()
            self.assertTrue(User.objects.get(pk=self.admin.pk).is_active)
            self.assertTrue(Token.objects.filter(pk=self.token.pk).exists())

    def test_an_unreadable_boutique_does_not_abort_the_callers_transaction(self):
        """The savepoint, tested with a schema that exists and is empty.

        A half-run migration is the case that reaches the database and fails
        there, and a failed statement inside an enclosing atomic() leaves the
        connection aborted -- every later query in that request then dies with
        'current transaction is aborted'. Swallowing the error is not enough on
        its own; without the per-tenant savepoint, one broken boutique takes the
        page down, which is exactly what the except was written to prevent.

        The two boutiques are named so the broken one sorts first, because a
        savepoint that did not roll back would be visible in the good one's
        result rather than in its own.
        """
        with ghost_tenant('sa_gh_half', 'owner@gh4.test', 'Half Atelier',
                          empty_schema=True), \
                temporary_tenant('sa_gh_whole', 'owner@gh5.test', 'Whole Atelier'):
            with schema_context('sa_gh_whole'):
                User.objects.create_user(username='real@gh5.test')

            with transaction.atomic():
                body = list_users(boutiques())
                self.assertEqual(body['unreadable'], ['sa_gh_half'])
                self.assertEqual([r['username'] for r in body['users']],
                                 ['real@gh5.test'])

                # search keeps its own copy of the savepoint, so it is asked the
                # same question rather than assumed to behave.
                users = [h for h in search('real@gh5', boutiques())
                         if h['type'] == 'user']
                self.assertEqual([h['boutique'] for h in users], ['sa_gh_whole'])

                # The transaction the caller opened is still usable, which is
                # the whole claim.
                self.assertTrue(BoutiqueTenant.objects.exists())


class QueryParameterTests(TransactionTestCase):
    """Numbers that arrive from a URL as strings.

    page, page_size and limit_per_type are wired straight from
    request.query_params. A bare int() turned '?page=abc' into a ValueError, an
    HTTP 500 and -- now that core.exceptions records them -- an ErrorEvent on
    the console's own error screen, reporting a mistyped URL as a platform
    fault.
    """

    def setUp(self):
        connection.set_schema_to_public()

    def test_junk_falls_back_and_numbers_are_clamped(self):
        for junk in ('abc', '', None, '12abc', '3.7', [], {}):
            self.assertEqual(clamped_int(junk, 50, 1, 200), 50, junk)

        self.assertEqual(clamped_int('25', 50, 1, 200), 25)
        self.assertEqual(clamped_int('-5', 50, 1, 200), 1)
        self.assertEqual(clamped_int(0, 50, 1, 200), 1)
        self.assertEqual(clamped_int('9' * 40, 50, 1, 200), 200)
        # No ceiling on a page NUMBER: an out-of-range page is an empty slice of
        # a list already in memory, so there is nothing to bound.
        self.assertEqual(clamped_int('100000', 1), 100000)

    def test_list_users_serves_a_malformed_page_rather_than_failing(self):
        with temporary_tenant('sa_qp', 'owner@qp.test', 'Paged Atelier'):
            with schema_context('sa_qp'):
                User.objects.create_user(username='owner@qp.test',
                                         email='owner@qp.test')

            tenants = boutiques()
            for page, size in (('abc', 'abc'), ('', ''), (None, None),
                               ('-3', '-3'), ('9' * 40, '9' * 40)):
                body = list_users(tenants, page=page, page_size=size)
                self.assertGreaterEqual(body['page'], 1)
                self.assertGreaterEqual(body['page_size'], 1)
                self.assertLessEqual(body['page_size'], MAX_PAGE_SIZE)
                self.assertEqual(body['count'], 1)

            body = list_users(tenants, page='abc', page_size='')
            self.assertEqual((body['page'], body['page_size']),
                             (1, DEFAULT_PAGE_SIZE))
            self.assertEqual(len(body['users']), 1)

            # A page past the end is empty, not an error -- and page 1 is still
            # page 1 after a huge page_size clamps.
            self.assertEqual(list_users(tenants, page='9' * 40)['users'], [])


class BoutiqueRowTests(TransactionTestCase):
    """What one boutique's row on the Boutiques screen says about money.

    This belongs beside the other console tests in superadmin/tests.py and is
    here only because that file is not part of this change. It is worth pinning:
    the serializer emitted `revenue` and not `collected`, so every row showed an
    em-dash in a Collected column that the platform total above it filled with a
    real figure -- and the two numbers are not interchangeable (metrics.py:
    revenue is BOOKED, collected is CASH).
    """

    def setUp(self):
        connection.set_schema_to_public()

    def test_a_row_reports_cash_as_well_as_booked(self):
        with temporary_tenant('sa_row', 'owner@row.test', 'Row Atelier') as tenant:
            with schema_context('sa_row'):
                customer = Customer.objects.create(first_name='Paying',
                                                   last_name='Customer',
                                                   mobile_number='9000009999')
                Order.objects.create(order_id='ROW-1', customer=customer,
                                     total_amount=1000, amount_paid=250,
                                     order_status='Received')

            row = TenantSerializer(tenant).data
            # float, not Decimal: DRF renders Decimal as a quoted string the
            # portal would have to parse before adding anything up.
            self.assertEqual((row['revenue'], row['collected']), (1000.0, 250.0))
            self.assertIsInstance(row['collected'], float)

    def test_an_unreadable_boutique_reports_no_figure_rather_than_zero(self):
        with ghost_tenant('sa_row_gh', 'owner@rowgh.test', 'Ghost Row') as ghost:
            row = TenantSerializer(ghost).data
            self.assertIs(row['healthy'], False)
            # None, not 0: a boutique that could not be read has not collected
            # nothing, it is unknown, and the column renders it as such.
            self.assertIsNone(row['collected'])
            self.assertIsNone(row['revenue'])


class AccessLinkTests(TransactionTestCase):
    """Handing a boutique its access without anybody learning a password.

    The properties under test are the reasons this exists rather than a
    "show me their password" button, so each is asserted rather than assumed.
    """

    def setUp(self):
        connection.set_schema_to_public()

    def test_link_sets_a_password_signs_in_and_then_stops_working(self):
        with temporary_tenant('al_flow', 'owner@al.test', 'Link Atelier') as tenant:
            with schema_context('al_flow'):
                User.objects.create_user(username='owner@al.test',
                                         email='owner@al.test',
                                         password='the-original-password')

            ok, message, data = issue_access_link('al_flow', 'owner@al.test')
            self.assertTrue(ok, message)
            self.assertIn('reset=', data['link'])

            payload = data['link'].split('reset=')[1]
            chosen = 'TheOwnerChose2026!x'

            client = APIClient()
            self.assertEqual(client.post('/api/auth/password-reset/confirm/',
                                         {'token': payload, 'password': chosen},
                                         format='json').status_code, 200)

            signed_in = client.post('/api/auth/login/',
                                    {'username': 'owner@al.test', 'password': chosen},
                                    format='json')
            self.assertEqual(signed_in.status_code, 200)
            self.assertEqual(signed_in.json()['user']['role'], 'Owner')

            # Single use. The token derives from the password hash, so setting a
            # password invalidates the link that set it -- which is what makes
            # it safe to send over a channel that keeps history.
            self.assertEqual(client.post('/api/auth/password-reset/confirm/',
                                         {'token': payload, 'password': 'Another2026!x'},
                                         format='json').status_code, 400)
            self.assertIs(tenant.is_active, True)

    def test_works_for_an_account_with_no_email_on_file(self):
        """The case trigger_password_reset must refuse and this must not.

        Staff accounts are created by the boutique through the roster and do not
        always carry an address; those are exactly the people an administrator
        is asked to get signed in.
        """
        with temporary_tenant('al_noemail', 'owner@ne.test', 'No Email Atelier'):
            with schema_context('al_noemail'):
                User.objects.create_user(username='tailor-no-address', password='x')

            ok, message, data = issue_access_link('al_noemail', 'tailor-no-address')
            self.assertTrue(ok, message)
            self.assertIn('reset=', data['link'])
            self.assertFalse(data['emailed'])

            refused_ok, _refused_message = trigger_password_reset(
                'al_noemail', 'tailor-no-address')
            self.assertFalse(refused_ok)

    def test_refused_for_a_suspended_boutique_and_a_deactivated_account(self):
        with temporary_tenant('al_susp', 'owner@su.test', 'Suspended Atelier') as tenant:
            with schema_context('al_susp'):
                User.objects.create_user(username='owner@su.test',
                                         email='owner@su.test', password='x')
                User.objects.create_user(username='gone', password='x', is_active=False)

            ok, message, data = issue_access_link('al_susp', 'gone')
            self.assertFalse(ok)
            self.assertIsNone(data)
            self.assertIn('deactivated', message)

            BoutiqueTenant.objects.filter(pk=tenant.pk).update(is_active=False)
            clear_tenant_cache()
            # The confirm view refuses a suspended boutique, so a link issued
            # here would be dead on arrival. Refuse now, with the real reason.
            ok, message, data = issue_access_link('al_susp', 'owner@su.test')
            self.assertFalse(ok)
            self.assertIn('suspended', message)

    def test_the_endpoint_returns_the_link_but_the_audit_trail_does_not(self):
        """A trail holding live credentials is a second place to steal them."""
        from superadmin.models import AuditLog

        with temporary_tenant('al_audit', 'owner@au.test', 'Audit Atelier'):
            with schema_context('al_audit'):
                User.objects.create_user(username='owner@au.test',
                                         email='owner@au.test', password='x')

            response = admin_client().post(
                '/api/superadmin/users/al_audit/owner@au.test/access-link/',
                {'reason': 'owner locked out, verified by phone'}, format='json')
            self.assertEqual(response.status_code, 200)
            link = response.json()['link']
            self.assertIn('reset=', link)

            connection.set_schema_to_public()
            entry = AuditLog.objects.filter(action='user.access_link').first()
            self.assertIsNotNone(entry)
            self.assertEqual(entry.target, 'owner@au.test')
            self.assertEqual(entry.boutique, 'al_audit')
            self.assertEqual(entry.reason, 'owner locked out, verified by phone')
            # The whole point: the record says a link was issued, not what it was.
            self.assertNotIn('reset=', str(entry.after))
            self.assertNotIn(link, str(entry.after))
