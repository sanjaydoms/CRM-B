"""Tests for the public tracking page and the customer message log.

The tracking page is the only route in the project a stranger reaches with no
token and no X-Tenant-ID header, and it reads across schemas to do it -- so what
is pinned here is that a genuine link resolves to exactly one boutique's order,
and that anything else (edited token, dead schema, unknown order) is a 404 and
not a 500 or, worse, another boutique's data.
"""

from django.core import signing
from django.db import connection
from django.test import Client
from django.test.utils import override_settings
from django_tenants.test.cases import TenantTestCase

from crm_api.models import BoutiqueSettings, Customer, CustomerMessage, Order
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
        self.assertIn("6000.00", body)
        self.assertIn("Partially Paid", body)


class CustomerMessageTests(TrackingTestBase):
    def test_order_creation_logs_a_message_carrying_the_tracking_link(self):
        message = CustomerMessage.objects.get(
            order=self.order, template_key='order_confirmation'
        )
        self.assertEqual(message.status, 'SENT')
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

    def _owner(self):
        from django.contrib.auth.models import User
        user, _ = User.objects.get_or_create(
            username='owner@tracking.test', defaults={'email': 'owner@tracking.test'}
        )
        return user
