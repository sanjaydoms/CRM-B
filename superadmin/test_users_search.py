
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
from superadmin.users import (DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, clamped_int,
                              list_users, revoke_sessions, set_user_active,
                              trigger_password_reset)
from tenants.models import BoutiqueTenant


def boutiques():
    connection.set_schema_to_public()
    return list(BoutiqueTenant.objects.exclude(schema_name='public'))


@contextmanager
def ghost_tenant(schema_name, owner_email, name, empty_schema=False):
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
            self.assertEqual(
                rows[('sa_us_a', 'cutter@usa.test')]['role'], 'Cutting Master')
            self.assertEqual(
                rows[('sa_us_b', 'owner@usb.test')]['role'], 'Owner')
            self.assertEqual(
                rows[('sa_us_b', 'owner@usb.test')]['boutique_name'], 'Atelier B')

    def test_an_owner_who_also_works_the_floor_is_still_the_owner(self):
        with temporary_tenant('sa_us_floor', 'owner@floor.test', 'Floor Atelier'):
            with schema_context('sa_us_floor'):
                owner = User.objects.create_user(username='owner@floor.test',
                                                 email='owner@floor.test')
                Tailor.objects.create(name='Owner', specialty='All',
                                      role='Master', user=owner)

            row = list_users(boutiques(), boutique='sa_us_floor')['users'][0]
            self.assertEqual(row['role'], 'Owner')
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
        with temporary_tenant('sa_ua_tok', 'owner@tok3.test', 'Token Atelier'):
            with schema_context('sa_ua_tok'):
                staff = User.objects.create_user(username='staff@tok3.test')
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
            self.assertNotIn(key, str(before))

            ok, _ = revoke_sessions('sa_ua_tok', 'staff@tok3.test')
            self.assertTrue(ok)
            self.assertEqual(call_api(), 401)

            after = list_users(boutiques(), boutique='sa_ua_tok')
            self.assertIs(after['users'][0]['has_token'], False)
            self.assertIs(after['users'][0]['is_active'], True)

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
            self.assertIn('?reset=sa_ua_pw.', mail.outbox[0].body)
            self.assertIn('Reset Atelier', mail.outbox[0].subject)

    def test_password_reset_refuses_a_deactivated_account(self):
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

            orders = [h for h in hits if h['type'] == 'order']
            self.assertEqual([o['id'] for o in orders], ['SE-1'])
            self.assertEqual(orders[0]['boutique'], 'sa_se_a')

            self.assertEqual(len({h['key'] for h in hits}), len(hits))

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
            self.assertEqual(users[0]['id'], 'hana@named.test')
            self.assertEqual(users[0]['boutique'], 'sa_se_named')

    def test_the_consoles_own_tables_are_searchable(self):
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

            for junk in ('abc', '', None, '12abc', [], '3.7'):
                self.assertEqual(len(customers(junk)), DEFAULT_PER_TYPE, junk)
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
            self.assertNotIn('platform@ghost.test', str(body))

    def test_search_does_not_attribute_the_platform_superuser_to_a_ghost(self):
        with ghost_tenant('sa_gh_find', 'owner@gh2.test', 'Ghost Two'):
            hits = search('platform@ghost.test', boutiques())
            self.assertEqual([h for h in hits if h['type'] == 'user'], [])

            hits = search('platform', boutiques())
            self.assertEqual([h for h in hits if h['type'] == 'user'], [])

        with ghost_tenant('sa_gh_empty', 'owner@gh6.test', 'Empty Atelier',
                          empty_schema=True):
            hits = search('platform', boutiques())
            self.assertEqual([h for h in hits if h['type'] == 'user'], [])

    def test_a_write_to_a_ghost_boutique_never_reaches_the_public_account(self):
        with ghost_tenant('sa_gh_write', 'owner@gh3.test', 'Ghost Three'):
            with self.assertRaises(MissingSchema):
                set_user_active('sa_gh_write', 'platform@ghost.test', False)

            with self.assertRaises(MissingSchema):
                revoke_sessions('sa_gh_write', 'platform@ghost.test')

            connection.set_schema_to_public()
            self.assertTrue(User.objects.get(pk=self.admin.pk).is_active)
            self.assertTrue(Token.objects.filter(pk=self.token.pk).exists())

    def test_an_unreadable_boutique_does_not_abort_the_callers_transaction(self):
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

                users = [h for h in search('real@gh5', boutiques())
                         if h['type'] == 'user']
                self.assertEqual([h['boutique'] for h in users], ['sa_gh_whole'])

                self.assertTrue(BoutiqueTenant.objects.exists())


class QueryParameterTests(TransactionTestCase):

    def setUp(self):
        connection.set_schema_to_public()

    def test_junk_falls_back_and_numbers_are_clamped(self):
        for junk in ('abc', '', None, '12abc', '3.7', [], {}):
            self.assertEqual(clamped_int(junk, 50, 1, 200), 50, junk)

        self.assertEqual(clamped_int('25', 50, 1, 200), 25)
        self.assertEqual(clamped_int('-5', 50, 1, 200), 1)
        self.assertEqual(clamped_int(0, 50, 1, 200), 1)
        self.assertEqual(clamped_int('9' * 40, 50, 1, 200), 200)
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

            self.assertEqual(list_users(tenants, page='9' * 40)['users'], [])


class BoutiqueRowTests(TransactionTestCase):

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
            self.assertEqual((row['revenue'], row['collected']), (1000.0, 250.0))
            self.assertIsInstance(row['collected'], float)

    def test_an_unreadable_boutique_reports_no_figure_rather_than_zero(self):
        with ghost_tenant('sa_row_gh', 'owner@rowgh.test', 'Ghost Row') as ghost:
            row = TenantSerializer(ghost).data
            self.assertIs(row['healthy'], False)
            self.assertIsNone(row['collected'])
            self.assertIsNone(row['revenue'])
