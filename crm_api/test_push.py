"""Who a push reaches, and who it must not.

The delivery mechanism is a stub here on purpose: what is worth testing is the
targeting. A notification that reaches the wrong phone in this product shows one
boutique's customer name and order to another member of staff, and a
notification that reaches no phone is the silence this whole feature exists to
end.
"""

from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import connection
from django.test import override_settings
from django_tenants.test.cases import TenantTestCase
from rest_framework.test import APIClient

from auth_tokens.services import issue_access
from crm_api.models import (
    BoutiqueSettings, Customer, DeviceToken, Notification, Order, Tailor,
)
from crm_api.push import push_notification, recipients_for


class PushTestBase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@push.test"
        tenant.name = "Push Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        BoutiqueSettings.objects.get_or_create(id=1)

        self.owner = User.objects.create_user(
            username="owner@push.test", email="owner@push.test", password="ownerpass123")
        self.cutter_user = User.objects.create_user(
            username="cutter@push.test", email="cutter@push.test", password="cutterpass123")
        self.finisher_user = User.objects.create_user(
            username="finisher@push.test", email="finisher@push.test", password="finishpass123")

        self.cutter = Tailor.objects.create(
            name="Meena", specialty="Cutting", role="Cutting Master",
            email="cutter@push.test", user=self.cutter_user)
        self.finisher = Tailor.objects.create(
            name="Latha", specialty="Finishing", role="Finishing Master",
            email="finisher@push.test", user=self.finisher_user)

        self.customer = Customer.objects.create(
            first_name="Anjali", last_name="Rao", mobile_number="9812345670",
            email_address="anjali@example.test")

    def register(self, user, token):
        return DeviceToken.objects.create(user=user, token=token)


class TargetingTests(PushTestBase):
    def test_an_owner_notification_reaches_the_owner_account(self):
        self.register(self.owner, 'owner-phone')
        note = Notification.objects.create(title="New Order", message="...",
                                           recipient_role="Owner")
        self.assertEqual([u.pk for u in recipients_for(note)], [self.owner.pk])

    def test_a_role_notification_reaches_everyone_holding_that_role(self):
        """A queue arrival is addressed to a role on purpose -- picking one of
        two QC Masters is the manual assignment the queue replaces."""
        second = User.objects.create_user(
            username="cutter2@push.test", email="cutter2@push.test", password="pass12345")
        Tailor.objects.create(name="Ravi", specialty="Cutting", role="Cutting Master",
                              email="cutter2@push.test", user=second)

        note = Notification.objects.create(title="Ready for Cutting", message="...",
                                           recipient_role="Cutting Master")
        self.assertEqual({u.pk for u in recipients_for(note)},
                         {self.cutter_user.pk, second.pk})

    def test_an_addressed_notification_reaches_only_that_person(self):
        note = Notification.objects.create(
            title="Your assignment", message="...", recipient_role="Cutting Master",
            recipient_email="cutter@push.test")
        self.assertEqual([u.pk for u in recipients_for(note)], [self.cutter_user.pk])

    def test_a_specialist_does_not_receive_another_specialists_work(self):
        note = Notification.objects.create(title="Ready for Finishing", message="...",
                                           recipient_role="Finishing Master")
        self.assertNotIn(self.cutter_user.pk, {u.pk for u in recipients_for(note)})

    def test_customer_notifications_reach_nobody(self):
        """Customers have no accounts in this product. A customer-addressed row
        exists for the tracking page and WhatsApp, and pushing it to a staff
        device would show one customer's message to the boutique's staff."""
        self.register(self.owner, 'owner-phone')
        note = Notification.objects.create(
            title="Order Update", message="Dear Anjali...", recipient_role="Customer",
            recipient_email="anjali@example.test")
        self.assertEqual(recipients_for(note), [])


class DeliveryTests(PushTestBase):
    def test_creating_a_notification_pushes_to_every_registered_device(self):
        """One owner, two devices -- the phone and the shop tablet."""
        self.register(self.owner, 'owner-phone')
        self.register(self.owner, 'owner-tablet')

        with patch('crm_api.push.get_backend', return_value=lambda messages: []):
            note = Notification.objects.create(title="New Order", message="...",
                                               recipient_role="Owner")
            self.assertEqual(push_notification(note), 2)

    def test_a_deactivated_device_is_skipped(self):
        device = self.register(self.owner, 'owner-phone')
        DeviceToken.objects.filter(pk=device.pk).update(is_active=False)
        with patch('crm_api.push.get_backend', return_value=lambda messages: []):
            note = Notification.objects.create(title="New Order", message="...",
                                               recipient_role="Owner")
            self.assertEqual(push_notification(note), 0)

    def test_a_token_fcm_rejects_is_deactivated(self):
        """Otherwise every later send wastes a call on an uninstalled app."""
        self.register(self.owner, 'dead-token')
        with patch('crm_api.push.get_backend',
                   return_value=lambda messages: ['dead-token']):
            note = Notification.objects.create(title="New Order", message="...",
                                               recipient_role="Owner")
            push_notification(note)
        self.assertFalse(DeviceToken.objects.get(token='dead-token').is_active)

    def test_a_transport_failure_does_not_reach_the_caller(self):
        """The order transition that raised this has already committed. A failed
        push must not become an exception in a workflow."""
        self.register(self.owner, 'owner-phone')

        def explode(messages):
            raise RuntimeError('FCM is down')

        with patch('crm_api.push.get_backend', return_value=explode):
            note = Notification.objects.create(title="New Order", message="...",
                                               recipient_role="Owner")
            self.assertEqual(push_notification(note), 0)

    def test_the_payload_names_the_order_so_a_tap_can_open_it(self):
        self.register(self.owner, 'owner-phone')
        order = Order.objects.create(order_id='T2B-260101-0042', customer=self.customer)
        captured = []

        with patch('crm_api.push.get_backend',
                   return_value=lambda messages: captured.extend(messages) or []):
            note = Notification.objects.create(
                title="Order moved", message="...", recipient_role="Owner", order=order)
            push_notification(note)

        self.assertEqual(captured[0]['data']['order_id'], 'T2B-260101-0042')
        self.assertEqual(captured[0]['data']['type'], 'order')

    def test_an_order_event_carries_its_order_through_to_the_push(self):
        """End to end through the real fan-out rather than a hand-made row: the
        twenty-odd call sites are what would drift, not the payload builder."""
        from domains.orders.notifications import create_order_notifications
        order = Order.objects.create(order_id='T2B-260101-0043', customer=self.customer)

        create_order_notifications(order, created=True)

        owner_note = Notification.objects.filter(recipient_role='Owner').first()
        self.assertIsNotNone(owner_note)
        self.assertEqual(owner_note.order_id, order.pk)


class WiringTests(PushTestBase):
    """The glue, which fails silently when it is wrong."""

    def test_the_push_receiver_is_connected_to_notification(self):
        """Registered in CrmApiConfig.ready(). If that config ever stops being
        the app's default -- a rename, an INSTALLED_APPS entry pointing
        elsewhere -- nothing raises: notifications keep being written, no phone
        ever rings, and the only symptom is silence."""
        from django.db.models.signals import post_save

        receivers = [r[0][0] for r in post_save.receivers]
        self.assertIn('crm_api.push', receivers,
                      'CrmApiConfig.ready() did not register the push receiver')

    def test_a_push_that_explodes_cannot_break_the_transition_that_caused_it(self):
        """The callback runs AFTER commit, and an exception there propagates out
        of the atomic block -- so an order that really did move would answer 500
        and be retried."""
        from crm_api.push import _push_quietly

        broken = Notification(title="x", message="y", recipient_role="Owner")
        with patch('crm_api.push.recipients_for',
                   side_effect=RuntimeError('the schema went away')):
            _push_quietly(broken)   # must not raise


class RegistrationTests(PushTestBase):
    def signed_in(self, user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {issue_access(user).key}',
                           HTTP_X_TENANT_ID=self.tenant.schema_name)
        return client

    def test_a_device_registers_against_the_caller(self):
        response = self.signed_in(self.cutter_user).post(
            '/api/devices/', {'token': 'fcm-abc', 'platform': 'android'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(DeviceToken.objects.get(token='fcm-abc').user_id, self.cutter_user.pk)

    def test_registering_the_same_token_again_moves_it_rather_than_duplicating(self):
        """A shop phone handed to the next shift must stop delivering the
        previous holder's notifications."""
        self.signed_in(self.cutter_user).post(
            '/api/devices/', {'token': 'shared-phone'}, format='json')
        self.signed_in(self.finisher_user).post(
            '/api/devices/', {'token': 'shared-phone'}, format='json')

        self.assertEqual(DeviceToken.objects.filter(token='shared-phone').count(), 1)
        self.assertEqual(DeviceToken.objects.get(token='shared-phone').user_id,
                         self.finisher_user.pk)

    def test_a_device_cannot_be_registered_without_signing_in(self):
        response = APIClient().post('/api/devices/', {'token': 'x'}, format='json')
        self.assertIn(response.status_code, (401, 403))

    def test_signing_out_stops_delivery_to_that_device(self):
        client = self.signed_in(self.cutter_user)
        client.post('/api/devices/', {'token': 'fcm-abc'}, format='json')
        response = client.delete('/api/devices/', {'token': 'fcm-abc'}, format='json')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(DeviceToken.objects.get(token='fcm-abc').is_active)

    def test_one_staff_member_cannot_deactivate_another_persons_device(self):
        self.signed_in(self.cutter_user).post(
            '/api/devices/', {'token': 'cutter-phone'}, format='json')
        response = self.signed_in(self.finisher_user).delete(
            '/api/devices/', {'token': 'cutter-phone'}, format='json')

        self.assertEqual(response.status_code, 204)
        self.assertTrue(DeviceToken.objects.get(token='cutter-phone').is_active)

    @override_settings(PUSH_BACKEND='')
    def test_the_default_backend_delivers_nowhere_and_raises_nothing(self):
        """The shipped configuration. A boutique with no Firebase project must
        still be able to take an order."""
        self.register(self.owner, 'owner-phone')
        note = Notification.objects.create(title="New Order", message="...",
                                           recipient_role="Owner")
        self.assertEqual(push_notification(note), 1)
