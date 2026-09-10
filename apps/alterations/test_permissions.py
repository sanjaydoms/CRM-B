"""Who may do what, and the wall between one boutique and the next."""

from decimal import Decimal

from django.db import connection
from django.contrib.auth.models import User
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.alterations.models import AlterationRequest, AlterationStatus, AlterationType
from apps.alterations.testbase import AlterationTestCase
from domains.alterations import services
from domains.alterations.workflow import available_actions

BASE = '/api/alterations/'


class RolePermissionTests(AlterationTestCase):

    def setUp(self):
        super().setUp()
        self.alteration = services.create_alteration_request(
            customer_id=self.customer.id, order_id=self.order.order_id,
            garment_job_id=self.blouse.id,
            alteration_type=AlterationType.PAID_CLIENT_REQUEST,
            issue_description='Waist loose.', charge_amount=Decimal('600.00'),
            performed_by=self.owner, role='Owner')

    def as_owner(self, fn, **kw):
        return fn(self.alteration.id, performed_by=self.owner, role='Owner', **kw)

    def advance_to_assigned(self, tailor=None):
        self.as_owner(services.start_inspection)
        self.as_owner(services.submit_for_approval)
        self.as_owner(services.approve_alteration)
        self.as_owner(services.assign_alteration,
                      tailor_id=(tailor or self.tailor).id)

    # -- the account nothing claims ---------------------------------------

    def test_a_role_less_account_can_do_nothing(self):
        """The state a removed staff member's un-revoked token lands in."""
        for fn, kw in (
            (services.start_inspection, {}),
            (services.approve_alteration, {}),
            (services.cancel_alteration, {'reason': 'x'}),
            (services.complete_alteration, {}),
        ):
            with self.assertRaises(PermissionError):
                fn(self.alteration.id, performed_by=self.rogue, role=None, **kw)

        with self.assertRaises(PermissionError):
            services.record_alteration_payment(
                self.alteration.id, amount=Decimal('10'),
                received_by=self.rogue, role=None)

        with self.assertRaises(PermissionError):
            services.record_alteration_material_usage(
                self.alteration.id, item_id=self.fabric.id, quantity=Decimal('1'),
                recorded_by=self.rogue, role=None)

    def test_a_role_less_account_is_refused_by_the_api(self):
        client = self.api_client(self.rogue)
        self.assertEqual(client.get(BASE).status_code, status.HTTP_403_FORBIDDEN)
        res = client.post(f'{BASE}{self.alteration.id}/start-inspection/', {},
                          format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_a_designer_is_refused(self):
        from apps.design_studio.models import Designer
        user = User.objects.create_user(username='dz@a.test', email='dz@a.test',
                                        password='x')
        Designer.objects.create(user=user, name='Dee')
        client = self.api_client(user)
        self.assertEqual(client.get(BASE).status_code, status.HTTP_403_FORBIDDEN)

    def test_available_actions_is_empty_without_a_role(self):
        self.assertEqual(available_actions(self.alteration, None), [])

    # -- counter work ------------------------------------------------------

    def test_a_bench_tailor_cannot_run_the_counter(self):
        for fn, kw in ((services.start_inspection, {}),
                       (services.approve_alteration, {}),
                       (services.complete_alteration, {}),
                       (services.cancel_alteration, {'reason': 'x'})):
            with self.assertRaises(PermissionError):
                fn(self.alteration.id, performed_by=self.tailor.user,
                   role='Tailor', **kw)

    def test_the_master_may_run_the_counter(self):
        alteration = services.start_inspection(
            self.alteration.id, performed_by=self.master.user, role='Master')
        self.assertEqual(alteration.status, AlterationStatus.INSPECTION)

    def test_a_bench_tailor_cannot_create_an_alteration(self):
        with self.assertRaises(PermissionError):
            services.create_alteration_request(
                customer_id=self.customer.id, order_id=self.order.order_id,
                garment_job_id=self.lehenga.id,
                performed_by=self.tailor.user, role='Tailor')

    # -- bench work --------------------------------------------------------

    def test_the_assigned_tailor_may_work_and_send_to_qc(self):
        self.advance_to_assigned()
        alteration = services.start_alteration_work(
            self.alteration.id, performed_by=self.tailor.user, role='Tailor',
            tailor_id=self.tailor.id)
        self.assertEqual(alteration.status, AlterationStatus.IN_PROGRESS)

        alteration = services.send_to_qc(
            self.alteration.id, performed_by=self.tailor.user, role='Tailor',
            tailor_id=self.tailor.id)
        self.assertEqual(alteration.status, AlterationStatus.QC)

    def test_an_unassigned_tailor_may_not_touch_someone_elses_work(self):
        self.advance_to_assigned()
        with self.assertRaises(PermissionError) as ctx:
            services.start_alteration_work(
                self.alteration.id, performed_by=self.other_tailor.user,
                role='Tailor', tailor_id=self.other_tailor.id)
        self.assertIn('not assigned to you', str(ctx.exception))

    # -- quality check -----------------------------------------------------

    def test_qc_master_may_pass_and_fail(self):
        self.advance_to_assigned()
        self.as_owner(services.start_alteration_work)
        self.as_owner(services.send_to_qc)

        alteration = services.fail_quality_check(
            self.alteration.id, reason='Uneven hem.',
            performed_by=self.qc.user, role='QC Master')
        self.assertEqual(alteration.status, AlterationStatus.IN_PROGRESS)

        self.as_owner(services.send_to_qc)
        alteration = services.pass_quality_check(
            self.alteration.id, performed_by=self.qc.user, role='QC Master')
        self.assertEqual(alteration.status, AlterationStatus.READY_FOR_PICKUP)

    def test_a_bench_tailor_cannot_sign_off_their_own_quality_check(self):
        self.advance_to_assigned()
        self.as_owner(services.start_alteration_work)
        self.as_owner(services.send_to_qc)
        with self.assertRaises(PermissionError):
            services.pass_quality_check(self.alteration.id,
                                        performed_by=self.tailor.user, role='Tailor')

    def test_qc_master_gets_no_back_door_onto_the_bench(self):
        """Failing a check is a QC action; starting work is not."""
        self.advance_to_assigned()
        with self.assertRaises(PermissionError):
            services.start_alteration_work(
                self.alteration.id, performed_by=self.qc.user, role='QC Master',
                tailor_id=self.qc.id)

    # -- money and stock ---------------------------------------------------

    def test_a_tailor_cannot_take_money(self):
        with self.assertRaises(PermissionError):
            services.record_alteration_payment(
                self.alteration.id, amount=Decimal('100'),
                received_by=self.tailor.user, role='Tailor')

    def test_the_master_may_take_money(self):
        payment = services.record_alteration_payment(
            self.alteration.id, amount=Decimal('100'),
            received_by=self.master.user, role='Master')
        self.assertEqual(payment.amount, Decimal('100.00'))

    def test_only_the_owner_may_consume_stock(self):
        for user, role in ((self.master.user, 'Master'), (self.tailor.user, 'Tailor')):
            with self.assertRaises(PermissionError):
                services.record_alteration_material_usage(
                    self.alteration.id, item_id=self.fabric.id,
                    quantity=Decimal('1'), recorded_by=user, role=role)

    # -- visibility --------------------------------------------------------

    def test_a_tailor_only_sees_their_own_alterations(self):
        self.advance_to_assigned(self.tailor)
        mine = services.create_alteration_request(
            customer_id=self.customer.id, order_id=self.order.order_id,
            garment_job_id=self.lehenga.id, performed_by=self.owner, role='Owner',
            alteration_type=AlterationType.FREE_BOUTIQUE_FAULT)

        listed = self.api_client(self.tailor.user).get(BASE).data
        numbers = {row['alteration_number'] for row in listed}
        self.assertIn(self.alteration.alteration_number, numbers)
        self.assertNotIn(mine.alteration_number, numbers)

    def test_the_owner_sees_everything(self):
        self.advance_to_assigned(self.tailor)
        services.create_alteration_request(
            customer_id=self.customer.id, order_id=self.order.order_id,
            garment_job_id=self.lehenga.id, performed_by=self.owner, role='Owner',
            alteration_type=AlterationType.FREE_BOUTIQUE_FAULT)
        self.assertEqual(len(self.api_client(self.owner).get(BASE).data), 2)

    def test_assigned_to_me_filter(self):
        self.advance_to_assigned(self.tailor)
        listed = self.api_client(self.tailor.user).get(f'{BASE}?assigned_to_me=1').data
        self.assertEqual(len(listed), 1)

    def test_available_actions_differ_by_role(self):
        self.advance_to_assigned()
        self.alteration.refresh_from_db()
        self.assertIn('start-work',
                      available_actions(self.alteration, 'Tailor', self.tailor.id))
        self.assertNotIn('start-work',
                         available_actions(self.alteration, 'Tailor',
                                           self.other_tailor.id))
        self.assertNotIn('record-material',
                         available_actions(self.alteration, 'Master'))
        self.assertIn('record-payment', available_actions(self.alteration, 'Master'))
        self.assertIn('record-material', available_actions(self.alteration, 'Owner'))

    def test_no_payment_action_is_offered_when_nothing_is_owed(self):
        free = services.create_alteration_request(
            customer_id=self.customer.id, order_id=self.order.order_id,
            garment_job_id=self.lehenga.id,
            alteration_type=AlterationType.FREE_BOUTIQUE_FAULT,
            performed_by=self.owner, role='Owner')
        self.assertNotIn('record-payment', available_actions(free, 'Owner'))

        services.record_alteration_payment(
            self.alteration.id, amount=Decimal('600.00'),
            received_by=self.owner, role='Owner')
        self.alteration.refresh_from_db()
        self.assertNotIn('record-payment', available_actions(self.alteration, 'Owner'))


class TenantIsolationTests(AlterationTestCase):
    """A boutique can never reach another boutique's alterations."""

    OTHER_SCHEMA = 'alt_other_tenant'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from tenants.models import BoutiqueTenant, Domain

        # Once for the whole class, not once per test. Saving a BoutiqueTenant
        # provisions a schema and runs every migration into it, which against a
        # remote database is minutes of work -- and all five tests want the
        # same empty rival boutique. It must also be created from the public
        # schema; TenantTestCase leaves the connection inside our own.
        connection.set_schema_to_public()
        cls.other = BoutiqueTenant(
            schema_name=cls.OTHER_SCHEMA, name='Rival Atelier',
            owner_email='rival@alterations.test')
        cls.other.save()
        Domain.objects.create(domain='alt-other.localhost', tenant=cls.other,
                              is_primary=True)

        with schema_context(cls.OTHER_SCHEMA):
            rival = User.objects.create_user(
                username='rival@alterations.test', email='rival@alterations.test',
                password='rivalpass123')
            cls.rival_token = Token.objects.create(user=rival).key

        connection.set_tenant(cls.tenant)

    @classmethod
    def tearDownClass(cls):
        from tenants.models import BoutiqueTenant
        connection.set_schema_to_public()
        with connection.cursor() as cursor:
            cursor.execute(f'DROP SCHEMA IF EXISTS "{cls.OTHER_SCHEMA}" CASCADE')
        BoutiqueTenant.objects.filter(schema_name=cls.OTHER_SCHEMA).delete()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.alteration = services.create_alteration_request(
            customer_id=self.customer.id, order_id=self.order.order_id,
            garment_job_id=self.blouse.id, charge_amount=Decimal('400.00'),
            performed_by=self.owner, role='Owner')

    def rival_client(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {self.rival_token}',
                           HTTP_X_TENANT_ID=self.OTHER_SCHEMA)
        return client

    def test_the_other_boutique_sees_an_empty_register(self):
        self.assertEqual(self.rival_client().get(BASE).data, [])

    def test_the_other_boutique_cannot_retrieve_by_id(self):
        res = self.rival_client().get(f'{BASE}{self.alteration.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_the_other_boutique_cannot_drive_the_workflow(self):
        res = self.rival_client().post(
            f'{BASE}{self.alteration.id}/start-inspection/', {}, format='json')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_the_other_boutique_cannot_take_a_payment_against_it(self):
        res = self.rival_client().post(
            f'{BASE}{self.alteration.id}/payments/', {'amount': '100.00'},
            format='json')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_the_row_does_not_exist_in_the_other_schema(self):
        with schema_context(self.OTHER_SCHEMA):
            self.assertEqual(AlterationRequest.objects.count(), 0)
        connection.set_tenant(self.tenant)
        self.assertEqual(AlterationRequest.objects.count(), 1)
