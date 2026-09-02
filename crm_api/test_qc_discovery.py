
from django.contrib.auth.models import User
from django.db import connection
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.permissions import stages_for_role, visible_customers, visible_orders
from crm_api.models import (
    BoutiqueSettings, Customer, Measurement, Notification, Order, Tailor,
)
from domains.orders.services import OrderService


class QCDiscoveryTestBase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@qc.test"
        tenant.name = "QC Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        BoutiqueSettings.objects.get_or_create(id=1)

        self.owner = User.objects.create_user(
            username="owner@qc.test", email="owner@qc.test", password="ownerpass123")
        self.master, self.master_client = self._staff("Rohit Mehra", "Master", "master@qc.test")
        self.tailor, self.tailor_client = self._staff("Anya Sharma", "Tailor", "tailor@qc.test")
        self.qc, self.qc_client = self._staff("Anand Rao", "QC Master", "qc@qc.test")
        self.presser, self.presser_client = self._staff(
            "Vimala Devi", "Pressing Staff", "press@qc.test")

    def _staff(self, name, role, email):
        user = User.objects.create_user(username=email, email=email, password="staffpass123")
        tailor = Tailor.objects.create(
            name=name, specialty="Bridal", role=role, status="Available", user=user)
        return tailor, self._client_for(user)

    def _client_for(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Token {token.key}',
                        HTTP_X_TENANT_ID=self.tenant.schema_name)
        return api

    def make_order(self, mobile="9800000001"):
        customer = Customer.objects.create(
            first_name="Meera", last_name="Nair", mobile_number=mobile,
            garment_type="Lehenga")
        Measurement.objects.create(customer=customer, bust=36, waist=30, hips=38)
        return OrderService.create_order_for_customer(customer, {
            "base_price": 20000, "tailor_id": self.tailor.id,
            "master_id": self.master.id,
        }, user=self.owner)

    def reach(self, order, key):

        config = BoutiqueSettings.objects.get(id=1).workflow_config
        keys = [s["key"] for s in config]
        for earlier in keys[:keys.index(key)]:
            stage = order.stages.filter(stage_key=earlier).first()
            if stage is None or stage.status in ("COMPLETED", "SKIPPED"):
                continue
            optional = next((s.get("optional") for s in config if s["key"] == earlier), False)
            OrderService.transition_order_stage(
                order=order, stage_key=earlier,
                new_status="SKIPPED" if optional else "COMPLETED", user=self.owner)
        return Order.objects.get(pk=order.pk)

    def visible_ids(self, user):
        return set(visible_orders(Order.objects.all(), user).values_list('order_id', flat=True))


class RoleStageDeclarationTests(QCDiscoveryTestBase):


    def test_the_queue_is_built_from_the_same_roles_list_the_engine_enforces(self):
        config = BoutiqueSettings.objects.get(id=1).workflow_config
        self.assertEqual(stages_for_role(config, 'QC Master'), ['master_quality_check'])
        self.assertEqual(stages_for_role(config, 'Pressing Staff'), ['pressing'])
        self.assertEqual(stages_for_role(config, 'Designer'), [])

    def test_a_renamed_role_moves_visibility_with_it(self):
        settings = BoutiqueSettings.objects.get(id=1)
        for stage in settings.workflow_config:
            if stage['key'] == 'master_quality_check':
                stage['roles'] = ['Owner', 'Master']
        settings.save()

        order = self.reach(self.make_order(), 'master_quality_check')
        self.assertNotIn(order.order_id, self.visible_ids(self.qc.user),
                         'QC Master no longer performs the stage, so it leaves their queue')


class QCQueueTests(QCDiscoveryTestBase):
    def test_an_order_that_reaches_qc_appears_without_anyone_assigning_it(self):
        order = self.reach(self.make_order(), 'master_quality_check')

        self.assertIsNone(order.stages.get(stage_key='master_quality_check').assigned_to,
                          'nobody assigned this -- that is the point')
        self.assertIn(order.order_id, self.visible_ids(self.qc.user))

    def test_an_order_still_in_stitching_is_not_in_the_qc_queue(self):
        order = self.reach(self.make_order(), 'stitching_in_progress')
        self.assertNotIn(order.order_id, self.visible_ids(self.qc.user))

    def test_a_fresh_order_is_in_nobodys_specialist_queue(self):
        order = self.make_order()
        self.assertNotIn(order.order_id, self.visible_ids(self.qc.user))
        self.assertNotIn(order.order_id, self.visible_ids(self.presser.user))

    def test_the_order_leaves_the_queue_once_qc_is_done(self):
        order = self.reach(self.make_order(), 'master_quality_check')
        self.assertIn(order.order_id, self.visible_ids(self.qc.user))

        OrderService.transition_order_stage(
            order=order, stage_key='master_quality_check',
            new_status='COMPLETED', user=self.qc.user)

        self.assertNotIn(order.order_id, self.visible_ids(self.qc.user),
                         'finished work is not still waiting')

    def test_each_specialist_sees_only_their_own_stage(self):
        pressing_order = self.reach(self.make_order("9800000002"), 'pressing')
        qc_order = self.reach(self.make_order("9800000003"), 'master_quality_check')

        self.assertEqual(self.visible_ids(self.presser.user), {pressing_order.order_id})
        self.assertEqual(self.visible_ids(self.qc.user), {qc_order.order_id})

    def test_a_manual_assignment_still_works_alongside_the_queue(self):
        order = self.reach(self.make_order(), 'pressing')
        self.assertNotIn(order.order_id, self.visible_ids(self.qc.user))

        response = self.master_client.post(
            reverse('order-assign-stage', args=[order.id]),
            {'stage_key': 'master_quality_check', 'tailor_id': self.qc.id}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn(order.order_id, self.visible_ids(self.qc.user))

    def test_the_queue_reaches_the_orders_api_the_dashboard_reads(self):
        order = self.reach(self.make_order(), 'master_quality_check')
        response = self.qc_client.get(reverse('order-list'))
        self.assertEqual(response.status_code, 200)
        rows = response.data['results'] if isinstance(response.data, dict) else response.data
        self.assertEqual([r['order_id'] for r in rows], [order.order_id])

    def test_the_customer_behind_a_queued_order_resolves(self):
        order = self.reach(self.make_order(), 'master_quality_check')
        names = visible_customers(Customer.objects.all(), self.qc.user)
        self.assertEqual([c.first_name for c in names], ['Meera'])

    def test_a_tailor_does_not_inherit_the_whole_book(self):
        mine = self.reach(self.make_order("9800000004"), 'master_quality_check')
        other_tailor, _ = self._staff("Latha", "Tailor", "latha@qc.test")
        theirs = OrderService.create_order_for_customer(
            Customer.objects.create(first_name="Sita", last_name="R",
                                    mobile_number="9800000005", garment_type="Saree"),
            {"base_price": 5000, "tailor_id": other_tailor.id}, user=self.owner)
        self.assertNotIn(theirs.order_id, self.visible_ids(self.tailor.user))
        self.assertIn(mine.order_id, self.visible_ids(self.tailor.user))


class QCInspectionTests(QCDiscoveryTestBase):


    def test_the_qc_master_can_complete_the_inspection_they_found(self):
        order = self.reach(self.make_order(), 'master_quality_check')

        response = self.qc_client.post(
            reverse('order-transition-stage', args=[order.id]),
            {'stage_key': 'master_quality_check', 'status': 'COMPLETED',
             'comments': 'Hem even, beading secure.'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)

        order.refresh_from_db()
        self.assertEqual(order.stages.get(stage_key='master_quality_check').status,
                         'COMPLETED')
        self.assertEqual(order.order_status, 'Ready for Dispatch')

    def test_the_role_boundary_still_holds_on_the_stages_that_are_not_theirs(self):
        order = self.reach(self.make_order(), 'master_quality_check')
        response = self.qc_client.post(
            reverse('order-transition-stage', args=[order.id]),
            {'stage_key': 'ready_for_delivery', 'status': 'COMPLETED'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('not authorized', str(response.data).lower())

    def test_a_presser_cannot_do_the_quality_check(self):
        order = self.reach(self.make_order(), 'master_quality_check')
        response = self.presser_client.post(
            reverse('order-transition-stage', args=[order.id]),
            {'stage_key': 'master_quality_check', 'status': 'COMPLETED'}, format='json')
        self.assertIn(response.status_code, (400, 403, 404))
        order.refresh_from_db()
        self.assertEqual(order.stages.get(stage_key='master_quality_check').status,
                         'NOT_STARTED')


class QueueNotificationTests(QCDiscoveryTestBase):
    def test_finishing_pressing_notifies_the_qc_role(self):
        order = self.reach(self.make_order(), 'pressing')
        Notification.objects.all().delete()

        OrderService.transition_order_stage(
            order=order, stage_key='pressing', new_status='COMPLETED', user=self.owner)

        qc_notes = Notification.objects.filter(recipient_role='QC Master')
        self.assertEqual(qc_notes.count(), 1, 'exactly one, addressed to the role')
        self.assertIn(order.order_id, qc_notes.get().message)

    def test_the_notification_is_addressed_to_the_role_not_a_person(self):
        self._staff("Second Inspector", "QC Master", "qc2@qc.test")
        order = self.reach(self.make_order(), 'pressing')
        Notification.objects.all().delete()

        OrderService.transition_order_stage(
            order=order, stage_key='pressing', new_status='COMPLETED', user=self.owner)

        note = Notification.objects.get(recipient_role='QC Master')
        self.assertEqual(note.recipient_email or '', '')

    def test_both_qc_masters_can_read_it(self):
        second, second_client = self._staff("Second Inspector", "QC Master", "qc2@qc.test")
        order = self.reach(self.make_order(), 'pressing')
        OrderService.transition_order_stage(
            order=order, stage_key='pressing', new_status='COMPLETED', user=self.owner)

        for client in (self.qc_client, second_client):
            response = client.get(reverse('notification-list'))
            self.assertEqual(response.status_code, 200)
            rows = response.data['results'] if isinstance(response.data, dict) else response.data
            self.assertTrue(any(order.order_id in r['message'] for r in rows))

    def test_starting_a_stage_announces_nothing(self):
        order = self.reach(self.make_order(), 'pressing')
        Notification.objects.all().delete()
        OrderService.transition_order_stage(
            order=order, stage_key='pressing', new_status='IN_PROGRESS', user=self.owner)
        self.assertFalse(Notification.objects.filter(recipient_role='QC Master').exists())

    def test_no_notification_for_a_role_nobody_holds(self):
        Tailor.objects.filter(role='QC Master').delete()
        order = self.reach(self.make_order(), 'pressing')
        Notification.objects.all().delete()
        OrderService.transition_order_stage(
            order=order, stage_key='pressing', new_status='COMPLETED', user=self.owner)
        self.assertFalse(Notification.objects.filter(recipient_role='QC Master').exists())

    def test_the_notification_names_the_stage_that_is_waiting(self):
        order = self.reach(self.make_order(), 'pressing')
        Notification.objects.all().delete()
        OrderService.transition_order_stage(
            order=order, stage_key='pressing', new_status='COMPLETED', user=self.owner)
        note = Notification.objects.get(recipient_role='QC Master')
        self.assertIn('Master Quality Check', note.title)
