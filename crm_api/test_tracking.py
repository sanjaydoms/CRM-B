"""Tests for the public tracking page and the customer message log.

The tracking page is the only route in the project a stranger reaches with no
token and no X-Tenant-ID header, and it reads across schemas to do it -- so what
is pinned here is that a genuine link resolves to exactly one boutique's order,
and that anything else (edited token, dead schema, unknown order) is a 404 and
not a 500 or, worse, another boutique's data.
"""

import importlib
import io
import os
import shutil
import tempfile
from unittest import mock
from urllib.parse import quote

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import signing
from django.db import connection
from django.test import Client, SimpleTestCase
from django.test.utils import override_settings
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from crm_api.models import (
    BoutiqueSettings, Customer, CustomerMessage, GarmentImage, Order, Tailor,
    whatsapp_number,
)
from domains.orders.messaging import send_customer_message
from domains.orders.services import OrderService
from domains.orders.tracking import SALT, build_token, read_token, tracking_url


def exploding_backend(message):
    raise RuntimeError("provider unreachable")


DELIVERED = []


def recording_backend(message):
    DELIVERED.append(message.pk)
    return 'provider-id-1'


class TrackingTestBase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@tracking.test"
        tenant.name = "Tracking Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)

        self.boutique, _ = BoutiqueSettings.objects.get_or_create(id=1)
        self.boutique.name = "Meera Couture"
        self.boutique.phone = "+91 9000000001"
        self.boutique.save()

        self.customer = Customer.objects.create(
            first_name="Anita", last_name="Rao",
            mobile_number="+919000000002",
            email_address="anita@example.com",
            garment_type="Lehenga",
        )
        # Delivery is deferred to on_commit, and a TestCase never commits, so
        # the callbacks are run explicitly wherever a test asserts on what was
        # actually delivered.
        with self.captureOnCommitCallbacks(execute=True):
            self.order = OrderService.create_order_for_customer(self.customer, {})

    def _owner(self):
        """A user with no staff profile, which core.roles resolves to Owner."""
        user, _ = User.objects.get_or_create(
            username='owner@tracking.test', defaults={'email': 'owner@tracking.test'}
        )
        return user

    def tenant_client_get(self, url):
        """GET as a customer would: no auth, no tenant header, unknown host.

        The request resets the connection's schema on its way through the
        middleware, so the tenant is restored afterwards for the assertions.
        """
        response = Client().get(url)
        connection.set_tenant(self.tenant)
        return response


class TokenTests(TrackingTestBase):
    def test_token_round_trips_to_schema_and_order(self):
        schema, order_id = read_token(build_token(self.order))
        self.assertEqual(schema, self.tenant.schema_name)
        self.assertEqual(order_id, self.order.order_id)

    def test_edited_token_is_rejected(self):
        token = build_token(self.order)
        tampered = token[:-1] + ("x" if token[-1] != "x" else "y")
        self.assertEqual(read_token(tampered), (None, None))

    def test_token_signed_with_another_salt_is_rejected(self):
        forged = signing.dumps(
            {'s': self.tenant.schema_name, 'o': self.order.order_id},
            salt='some.other.purpose',
        )
        self.assertEqual(read_token(forged), (None, None))

    def test_tracking_url_uses_configured_origin(self):
        with override_settings(TRACKING_BASE_URL='https://track.example.com/'):
            self.assertTrue(
                tracking_url(self.order).startswith('https://track.example.com/track/')
            )


class TrackingPageTests(TrackingTestBase):
    def test_page_renders_order_for_anonymous_visitor(self):
        response = self.tenant_client_get(f"/track/{build_token(self.order)}/")

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn(self.order.order_id, body)
        self.assertIn("Meera Couture", body)
        self.assertIn("Anita", body)
        # The workflow's first stage is completed at creation, so the timeline
        # has something real in it rather than an empty list.
        self.assertIn("Created", body)
        # Django's {# #} is single-line only, so a multi-line one renders as
        # visible text on the page. Caught once already; cheaper to pin.
        self.assertNotIn("{#", body)
        self.assertNotIn("{%", body)

    def test_page_is_not_cached_or_indexed(self):
        response = self.tenant_client_get(f"/track/{build_token(self.order)}/")
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertIn('noindex', response['X-Robots-Tag'])

    def test_edited_token_404s(self):
        token = build_token(self.order)
        tampered = token[:-1] + ("x" if token[-1] != "x" else "y")
        self.assertEqual(self.tenant_client_get(f"/track/{tampered}/").status_code, 404)

    def test_token_for_unknown_schema_404s(self):
        """A correctly signed token naming a schema that no longer exists.

        Without the tenant-table check this would put a dead schema on
        search_path and surface as a 500.
        """
        forged = signing.dumps({'s': 'gone_boutique', 'o': self.order.order_id}, salt=SALT)
        self.assertEqual(self.tenant_client_get(f"/track/{forged}/").status_code, 404)

    def test_token_for_public_schema_404s(self):
        forged = signing.dumps({'s': 'public', 'o': self.order.order_id}, salt=SALT)
        self.assertEqual(self.tenant_client_get(f"/track/{forged}/").status_code, 404)

    def test_unknown_order_404s(self):
        forged = signing.dumps({'s': self.tenant.schema_name, 'o': 'T2B-000000-0000'}, salt=SALT)
        self.assertEqual(self.tenant_client_get(f"/track/{forged}/").status_code, 404)

    def test_internal_stage_notes_are_not_published(self):
        """Staff type rework and blame into stage comments. It is not for the customer."""
        stage = self.order.stages.get(stage_key='created')
        stage.comments = "Ravi cut the sleeve wrong, re-cut from spare, don't tell the client"
        stage.save()

        response = self.tenant_client_get(f"/track/{build_token(self.order)}/")
        self.assertNotIn("don&#x27;t tell the client", response.content.decode())
        self.assertNotIn("re-cut from spare", response.content.decode())

    def test_missing_boutique_settings_is_not_invented_on_a_public_get(self):
        """An unauthenticated GET must not write, nor show the factory identity."""
        BoutiqueSettings.objects.all().delete()

        response = self.tenant_client_get(f"/track/{build_token(self.order)}/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Scaleezy Atelier", response.content.decode())
        self.assertNotIn("123 Atelier Way", response.content.decode())
        self.assertFalse(BoutiqueSettings.objects.exists())

    def test_payment_summary_shows_outstanding_balance(self):
        Order.objects.filter(pk=self.order.pk).update(total_amount=10000, amount_paid=4000)
        response = self.tenant_client_get(f"/track/{build_token(self.order)}/")

        body = response.content.decode()
        # Compared against the shared formatter rather than a literal: the page
        # prints Rs6,000 now, and pinning the string here would just re-record
        # whichever convention this screen happened to use.
        from core.formatting import format_money
        self.assertIn(format_money(6000), body)
        self.assertIn("Partially Paid", body)


class CustomerMessageTests(TrackingTestBase):
    def test_order_creation_queues_a_message_carrying_the_tracking_link(self):
        message = CustomerMessage.objects.get(
            order=self.order, template_key='order_confirmation'
        )
        # No transport is configured by default: the owner sends it themselves,
        # so it waits for them rather than claiming to have gone out.
        self.assertEqual(message.status, 'QUEUED')
        self.assertEqual(message.to_number, self.customer.mobile_number)
        self.assertIn('/track/', message.body)

        # The link in the message is the one that actually works.
        path = '/track/' + message.body.split('/track/')[1].strip().rstrip('/') + '/'
        self.assertEqual(self.tenant_client_get(path).status_code, 200)

    def test_stage_transition_logs_a_message(self):
        before = CustomerMessage.objects.filter(order=self.order).count()
        OrderService.transition_order_stage(
            self.order, 'measurements_completed', 'COMPLETED',
            user=self._owner(),
        )
        self.assertEqual(CustomerMessage.objects.filter(order=self.order).count(), before + 1)

    def test_disabled_messaging_writes_nothing(self):
        BoutiqueSettings.objects.filter(id=1).update(customer_messaging_enabled=False)
        self.assertIsNone(send_customer_message(self.order, 'manual', 'hello'))
        self.assertFalse(
            CustomerMessage.objects.filter(order=self.order, template_key='manual').exists()
        )

    @override_settings(CUSTOMER_MESSAGE_BACKEND='crm_api.test_tracking.exploding_backend')
    def test_transport_failure_is_recorded_not_raised(self):
        with self.captureOnCommitCallbacks(execute=True):
            message = send_customer_message(self.order, 'manual', 'hello')

        message.refresh_from_db()
        self.assertEqual(message.status, 'FAILED')
        self.assertIn('provider unreachable', message.error)

    @override_settings(CUSTOMER_MESSAGE_BACKEND='crm_api.test_tracking.recording_backend')
    def test_transport_runs_only_after_the_order_transaction_commits(self):
        """The transport must not be called inside the caller's transaction.

        Both callers are @transaction.atomic. A transport that touches the
        database -- any real one does -- aborts that transaction when it fails,
        and the follow-up save() recording the failure then raises inside the
        caller and rolls back the order. Deferring delivery past the commit is
        what makes 'the message failed' cost a message instead of an order.
        """
        DELIVERED.clear()
        customer = Customer.objects.create(
            first_name="Devi", last_name="Nair", mobile_number="+919000000003",
            garment_type="Saree",
        )
        order = OrderService.create_order_for_customer(customer, {})

        self.assertEqual(DELIVERED, [], "transport ran inside the order transaction")
        message = CustomerMessage.objects.get(order=order, template_key='order_confirmation')
        self.assertEqual(message.status, 'QUEUED')

    def test_repeated_stages_with_one_customer_status_send_one_message(self):
        """Several workflow stages map to one customer-facing status.

        measurements_completed and fabric_confirmed both mean 'Confirmed';
        pattern_cutting and maggam_work both mean 'Design & Creation'. Firing on
        every stage means the customer is told the same sentence twice in a row.
        views.py already gates its own path on the status having actually
        changed; the workflow engine has to do the same, or the boutique's
        WhatsApp account is the one that looks broken.
        """
        owner = self._owner()
        for stage in ['measurements_completed', 'fabric_confirmed', 'pattern_cutting', 'maggam_work']:
            OrderService.transition_order_stage(self.order, stage, 'COMPLETED', user=owner)

        bodies = list(
            CustomerMessage.objects
            .filter(order=self.order, template_key='stage_update')
            .values_list('body', flat=True)
        )
        self.assertEqual(len(bodies), len(set(bodies)), f"duplicate messages sent: {bodies}")

class WhatsAppNumberTests(TenantTestCase):
    """wa.me only accepts a full international number.

    Every customer number in the database is a bare ten-digit Indian one, so
    getting this wrong opens a chat with nobody -- silently, since the link
    still looks like a link.
    """

    def test_bare_national_number_gains_the_country_code(self):
        self.assertEqual(whatsapp_number('6303301002'), '916303301002')

    def test_number_written_internationally_is_left_alone(self):
        self.assertEqual(whatsapp_number('+919000000002'), '919000000002')

    def test_punctuation_and_spacing_are_stripped(self):
        self.assertEqual(whatsapp_number('+91 90000-00002'), '919000000002')
        self.assertEqual(whatsapp_number('63033 01002'), '916303301002')

    def test_a_number_already_carrying_a_country_code_is_not_doubled(self):
        self.assertEqual(whatsapp_number('916303301002'), '916303301002')

    def test_national_trunk_zero_is_dropped(self):
        """'098765 43211' is how the number is written for domestic dialling.

        Kept, it produces wa.me/09876543211, which WhatsApp rejects -- while
        still rendering as a perfectly ordinary "Open WhatsApp" button.
        """
        self.assertEqual(whatsapp_number('098765 43211'), '919876543211')

    def test_international_access_code_is_dropped(self):
        self.assertEqual(whatsapp_number('0091 9876543211'), '919876543211')

    def test_trunk_zero_after_a_country_code_is_dropped(self):
        self.assertEqual(whatsapp_number('+91 (0) 98765 43211'), '919876543211')

    def test_a_ten_digit_number_starting_91_still_gets_the_country_code(self):
        """Indian mobiles legitimately start 91, so length has to decide."""
        self.assertEqual(whatsapp_number('9198765432'), '919198765432')

    def test_a_foreign_international_number_passes_through(self):
        self.assertEqual(whatsapp_number('+44 20 7123 4567'), '442071234567')

    def test_something_that_cannot_be_a_number_yields_no_link(self):
        """Better no button than a button that opens a chat with a stranger."""
        self.assertEqual(whatsapp_number('12345'), '')
        self.assertEqual(whatsapp_number('9876543211 9876543211'), '')
        self.assertEqual(whatsapp_number('call the shop'), '')

    def test_empty_input_yields_no_link(self):
        self.assertEqual(whatsapp_number(''), '')
        self.assertEqual(whatsapp_number(None), '')

    @override_settings(WHATSAPP_COUNTRY_CODE='44')
    def test_country_code_is_configurable(self):
        self.assertEqual(whatsapp_number('6303301002'), '446303301002')


class ManualSendTests(TrackingTestBase):
    """The owner sends from their own WhatsApp; the CRM only removes the typing."""

    def setUp(self):
        super().setUp()
        self.owner = self._owner()
        self.tailor_user = User.objects.create_user(
            username='tailor@tracking.test', password='tailorpass123',
        )
        Tailor.objects.create(
            name='Anya', specialty='Lehenga', role='Tailor', user=self.tailor_user,
        )
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + Token.objects.create(user=self.owner).key,
            HTTP_X_TENANT_ID=self.tenant.schema_name,
        )

    def queued(self):
        return CustomerMessage.objects.get(
            order=self.order, template_key='order_confirmation'
        )

    def test_whatsapp_url_opens_the_customer_chat_with_the_body_prefilled(self):
        message = self.queued()
        url = message.whatsapp_url

        self.assertTrue(url.startswith('https://wa.me/919000000002?text='))
        # The body is urlencoded, so the tracking link survives intact.
        self.assertIn(quote('/track/'), url)
        self.assertIn(quote(self.order.order_id), url)

    def test_a_customer_with_no_number_yields_no_link_rather_than_a_broken_one(self):
        message = self.queued()
        message.to_number = ''
        self.assertEqual(message.whatsapp_url, '')

    def test_owner_lists_the_whole_boutique_queue_in_one_request(self):
        response = self.client.get(reverse('order-customer-messages'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        row = response.data[0]
        self.assertEqual(row['status'], 'QUEUED')
        self.assertEqual(row['template_key'], 'order_confirmation')
        self.assertEqual(row['order'], self.order.id)
        self.assertTrue(row['whatsapp_url'].startswith('https://wa.me/'))

    def test_the_queue_holds_only_what_is_still_waiting(self):
        message = self.queued()
        self.client.post(
            reverse('order-mark-message-sent', args=[self.order.id]),
            {'message_id': message.id}, format='json',
        )

        response = self.client.get(reverse('order-customer-messages'))
        self.assertEqual(response.data, [])

    def test_a_tailor_cannot_read_the_queue(self):
        """Each body carries the tracking link, which reaches the order's money.

        A tailor can see their own orders, but the role matrix keeps the
        financials from them -- and the tracking page shows the total, the
        amount paid and the balance to anyone holding the link.
        """
        response = self.tailor_client().get(reverse('order-customer-messages'))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_marks_a_message_sent(self):
        message = self.queued()
        response = self.client.post(
            reverse('order-mark-message-sent', args=[self.order.id]),
            {'message_id': message.id}, format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        message.refresh_from_db()
        self.assertEqual(message.status, 'SENT')
        self.assertEqual(message.sent_by, self.owner)

    def test_unknown_message_id_is_a_404(self):
        response = self.client.post(
            reverse('order-mark-message-sent', args=[self.order.id]),
            {'message_id': 999999}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_a_message_id_that_is_not_a_number_is_a_400_not_a_500(self):
        """id is a BigAutoField; an unparsable value is a bad request, not a crash."""
        for bad in ['abc', '', None, {'nope': 1}]:
            with self.subTest(message_id=bad):
                response = self.client.post(
                    reverse('order-mark-message-sent', args=[self.order.id]),
                    {'message_id': bad}, format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_message_belonging_to_another_order_cannot_be_marked_here(self):
        other_customer = Customer.objects.create(
            first_name="Devi", last_name="Nair", mobile_number="9800000123",
            garment_type="Saree",
        )
        other_order = OrderService.create_order_for_customer(other_customer, {})
        other_message = CustomerMessage.objects.filter(order=other_order).first()

        response = self.client.post(
            reverse('order-mark-message-sent', args=[self.order.id]),
            {'message_id': other_message.id}, format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        other_message.refresh_from_db()
        self.assertEqual(other_message.status, 'QUEUED')

    def tailor_client(self):
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION='Token ' + Token.objects.create(user=self.tailor_user).key,
            HTTP_X_TENANT_ID=self.tenant.schema_name,
        )
        return client

    def test_a_tailor_cannot_mark_messages_sent(self):
        """It goes out from the owner's phone, so it is the owner's to confirm."""
        message = self.queued()

        response = self.tailor_client().post(
            reverse('order-mark-message-sent', args=[self.order.id]),
            {'message_id': message.id}, format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        message.refresh_from_db()
        self.assertEqual(message.status, 'QUEUED')


def a_photograph(name='front.png', size=(400, 600)):
    """A real PNG, so the serializer's Pillow check has something to accept."""
    from PIL import Image
    buffer = io.BytesIO()
    Image.new('RGB', size, (180, 60, 90)).save(buffer, format='PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


class GarmentGalleryTests(TrackingTestBase):
    """Photographs of the finished garment, and when the customer may see them.

    MEDIA_ROOT is redirected per test, and the override is enabled by hand
    rather than with a class decorator. django_tenants' TenantTestCase.setUpClass
    does not call super(), so SimpleTestCase.setUpClass -- the code that enables
    a class-level override_settings -- never runs, and @override_settings on the
    class is a silent no-op. These tests write files; without this they write
    into the repository's own media/ directory.

    The cleanup deletes the directory it created, never settings.MEDIA_ROOT.
    Deleting whatever that setting happens to point at is how the real media
    directory got removed once already.
    """

    def setUp(self):
        super().setUp()

        media_root = tempfile.mkdtemp(prefix='tracking-test-media-')
        self.addCleanup(shutil.rmtree, media_root, ignore_errors=True)
        media_override = override_settings(MEDIA_ROOT=media_root)
        media_override.enable()
        self.addCleanup(media_override.disable)
        self.media_root = media_root

        self.owner = self._owner()
        self.master_user = User.objects.create_user(username='master@tracking.test')
        Tailor.objects.create(name='Rohit', specialty='Bridal', role='Master',
                              user=self.master_user)
        self.tailor_user = User.objects.create_user(username='tailor2@tracking.test')
        Tailor.objects.create(name='Anya', specialty='Lehenga', role='Tailor',
                              user=self.tailor_user)
        self.client = self.api_client(self.owner)

    def api_client(self, user):
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION='Token ' + Token.objects.create(user=user).key,
            HTTP_X_TENANT_ID=self.tenant.schema_name,
        )
        return client

    def upload(self, view='FRONT', client=None, image=None):
        return (client or self.client).post(
            reverse('order-upload-garment-image', args=[self.order.id]),
            {'view': view, 'image': image or a_photograph()}, format='multipart',
        )

    def publish(self, client=None, **data):
        return (client or self.client).post(
            reverse('order-publish-garment-images', args=[self.order.id]),
            data, format='json',
        )

    def test_uploads_land_in_the_test_media_root_not_the_repository(self):
        """Pins the override actually taking effect, which it silently did not."""
        from django.conf import settings

        self.assertEqual(settings.MEDIA_ROOT, self.media_root)
        self.upload('FRONT')
        image = GarmentImage.objects.get(order=self.order)
        self.assertTrue(image.image.path.startswith(self.media_root), image.image.path)

    def test_owner_uploads_a_front_view(self):
        response = self.upload('FRONT')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['view'], 'FRONT')
        self.assertEqual(response.data['view_label'], 'Front view')
        image = GarmentImage.objects.get(order=self.order)
        self.assertEqual(image.uploaded_by, self.owner)

    def test_uploading_the_same_view_replaces_it(self):
        self.upload('FRONT')
        first = GarmentImage.objects.get(order=self.order, view='FRONT')
        self.upload('FRONT', image=a_photograph('better-front.png'))

        images = GarmentImage.objects.filter(order=self.order, view='FRONT')
        self.assertEqual(images.count(), 1)
        self.assertNotEqual(images.first().id, first.id)

    def test_an_unknown_view_is_rejected(self):
        response = self.upload('SIDEWAYS')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(GarmentImage.objects.exists())

    def test_a_file_that_is_not_an_image_is_rejected(self):
        """A renamed file must fail here, not become a broken img on the page."""
        response = self.upload(
            'FRONT',
            image=SimpleUploadedFile('front.png', b'MZ\x90\x00 not a png',
                                     content_type='image/png'),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(GarmentImage.objects.exists())

    def test_uploading_nothing_is_rejected(self):
        response = self.client.post(
            reverse('order-upload-garment-image', args=[self.order.id]),
            {'view': 'FRONT'}, format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_deleting_an_image_removes_it(self):
        self.upload('FRONT')
        image = GarmentImage.objects.get(order=self.order)

        response = self.client.delete(
            reverse('order-delete-garment-image', args=[self.order.id, image.id])
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(GarmentImage.objects.exists())

    def test_publishing_needs_both_required_views(self):
        self.upload('FRONT')
        response = self.publish()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['missing'], ['BACK'])
        self.order.refresh_from_db()
        self.assertFalse(self.order.garment_images_published)

    def test_publishing_tells_the_customer_once(self):
        self.upload('FRONT')
        self.upload('BACK')

        response = self.publish()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.assertTrue(self.order.garment_images_published)

        messages = CustomerMessage.objects.filter(order=self.order, template_key='garment_ready')
        self.assertEqual(messages.count(), 1)
        self.assertIn('/track/', messages.first().body)

        # Swapping a photograph and publishing again must not tell them twice.
        self.upload('FRONT', image=a_photograph('front-v2.png'))
        self.publish()
        self.assertEqual(
            CustomerMessage.objects.filter(order=self.order, template_key='garment_ready').count(),
            1,
        )

    def test_unpublishing_hides_the_gallery_again(self):
        self.upload('FRONT')
        self.upload('BACK')
        self.publish()

        self.publish(published=False)

        self.order.refresh_from_db()
        self.assertFalse(self.order.garment_images_published)

    def test_the_customer_sees_nothing_until_it_is_published(self):
        self.upload('FRONT')
        self.upload('BACK')

        body = self.tenant_client_get(f"/track/{build_token(self.order)}/").content.decode()
        self.assertNotIn('Your outfit is ready', body)

        self.publish()
        body = self.tenant_client_get(f"/track/{build_token(self.order)}/").content.decode()
        self.assertIn('Your outfit is ready', body)
        self.assertIn('Front view', body)
        self.assertIn('Back view', body)

    def test_a_master_may_photograph_and_publish(self):
        """The specification has the owner or the master doing this."""
        master = self.api_client(self.master_user)
        self.assertEqual(self.upload('FRONT', client=master).status_code,
                         status.HTTP_201_CREATED)
        self.upload('BACK', client=master)
        self.assertEqual(self.publish(client=master).status_code, status.HTTP_200_OK)

    def test_a_tailor_may_not(self):
        response = self.upload('FRONT', client=self.api_client(self.tailor_user))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(GarmentImage.objects.exists())


class TrackingBaseUrlTests(SimpleTestCase):
    """Where a customer's link points, and which source wins.

    The failure this guards is silent and total: get the environment variable
    name wrong and every link a customer is sent points at localhost, which
    nothing in the application would notice.
    """

    def resolve(self, **env):
        import boutique_crm.settings as settings_module

        patched = dict(os.environ)
        for key in ('TRACKING_BASE_URL', 'RENDER_EXTERNAL_URL'):
            patched.pop(key, None)
        patched.update(env)

        with mock.patch.dict(os.environ, patched, clear=True):
            importlib.reload(settings_module)
            resolved = settings_module.TRACKING_BASE_URL
        # Leave the module as the rest of the run found it.
        importlib.reload(settings_module)
        return resolved

    def test_render_supplies_the_origin_with_nothing_configured(self):
        self.assertEqual(
            self.resolve(RENDER_EXTERNAL_URL='https://crm-b-sitt.onrender.com'),
            'https://crm-b-sitt.onrender.com',
        )

    def test_an_explicit_setting_beats_render(self):
        """A custom domain: RENDER_EXTERNAL_URL stays the onrender address."""
        self.assertEqual(
            self.resolve(
                TRACKING_BASE_URL='https://track.meeracouture.in',
                RENDER_EXTERNAL_URL='https://crm-b-sitt.onrender.com',
            ),
            'https://track.meeracouture.in',
        )

    def test_neither_falls_back_to_local_development(self):
        self.assertEqual(self.resolve(), 'http://localhost:8000')
