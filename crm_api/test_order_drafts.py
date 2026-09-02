"""A draft is not an order, and must not be able to become one by accident.

The wizard held six steps of work in browser memory and nowhere else, so a
refresh lost it -- and so did the empty-state "Add fabrics" button on step
four, which is the product's own advice to a boutique that has no fabric
library yet. A fully filled two-garment order, destroyed by following the
instruction on the screen. Because the customer was POSTed at step one, what
survived was an orphan customer with no order.

The persistence half of that is straightforward. The half worth guarding is
the other one: now that the workflow enforces real transitions and materials
follow production, a draft that leaked into the order tables would appear on a
tailor's dashboard, in the revenue figures, on a customer's tracking page, and
would reserve real cloth off a real shelf. So most of these tests are about
what a draft must NOT do.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.inventory.models import (
    Category, InventoryItem, OrderMaterialPlan, StockMovement, Unit,
)
from apps.inventory.services import InventoryService
from crm_api.models import (
    BoutiqueSettings, Customer, CustomerMessage, Order, OrderDraft, OrderStage,
    Tailor,
)
from domains.orders import drafts


class DraftTestBase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@drafts.test"
        tenant.name = "Drafts Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        from django.db import connection
        connection.set_tenant(self.tenant)

        self.owner = User.objects.create_user(
            username="owner@drafts.test", email="owner@drafts.test",
            password="ownerpass123")
        # A COLLEAGUE, not a nobody. The point of the intruder tests is that
        # somebody legitimately signed in still cannot read another person's
        # draft; before Phase 8 this account was silently the boutique owner
        # (no profile, so core.roles fell through to OWNER), which made the
        # assertion weaker than it looked. A Tailor profile makes it real staff.
        self.other = User.objects.create_user(
            username="other@drafts.test", email="other@drafts.test",
            password="otherpass123")
        Tailor.objects.create(name='Other', specialty='Blouses', role='Tailor',
                              user=self.other)
        BoutiqueSettings.objects.get_or_create(id=1)
        self.brocade = InventoryItem.objects.create(
            item_code='FAB-001', name='Maroon Brocade', category=Category.FABRIC,
            unit=Unit.METER, purchase_price=Decimal('100'), reorder_level=Decimal('5'))
        InventoryService.stock_in(self.brocade, Decimal('25'), user=self.owner,
                                  remarks='Opening')

    def client_for(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Token {token.key}',
                        HTTP_X_TENANT_ID=self.tenant.schema_name)
        return api

    WIZARD = {
        'first_name': 'Lakshmi', 'last_name': 'Iyer',
        'mobile_number': '919845012345', 'email_address': 'lakshmi@drafts.test',
        'address': '44 Church Street', 'customer_type': 'Women',
        'garments': [{'template': 'blouse', 'measurements': {'chest': '36'}}],
    }


class DraftSurvivalTests(DraftTestBase):
    """It has to still be there afterwards -- whatever "afterwards" was."""

    def test_a_draft_saved_at_one_step_comes_back_at_that_step(self):
        api = self.client_for(self.owner)
        created = api.post(reverse('order-draft-list'),
                           {'payload': self.WIZARD, 'current_step': 4}, format='json')
        self.assertEqual(created.status_code, 201)

        # A different client entirely: new token use, no shared memory. This is
        # what a refresh, a new tab, or signing in tomorrow all look like from
        # the server's side.
        reopened = self.client_for(self.owner).get(
            reverse('order-draft-detail', args=[created.data['id']]))
        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(reopened.data['current_step'], 4)
        self.assertEqual(reopened.data['payload']['first_name'], 'Lakshmi')
        self.assertEqual(len(reopened.data['payload']['garments']), 1)

    def test_a_draft_is_listed_so_the_wizard_can_offer_to_resume_it(self):
        api = self.client_for(self.owner)
        api.post(reverse('order-draft-list'),
                 {'payload': self.WIZARD, 'current_step': 2}, format='json')
        listed = api.get(reverse('order-draft-list'))
        self.assertEqual(len(listed.data), 1)
        self.assertEqual(listed.data[0]['customer_name'], 'Lakshmi')

    def test_a_draft_belongs_to_the_person_writing_it(self):
        api = self.client_for(self.owner)
        created = api.post(reverse('order-draft-list'),
                           {'payload': self.WIZARD}, format='json')
        intruder = self.client_for(self.other)
        self.assertEqual(len(intruder.get(reverse('order-draft-list')).data), 0)
        self.assertEqual(
            intruder.get(reverse('order-draft-detail',
                                 args=[created.data['id']])).status_code, 404)

    def test_abandoning_a_draft_removes_it_and_leaves_the_client_alone(self):
        customer = Customer.objects.create(
            first_name='Lakshmi', last_name='Iyer', mobile_number='919845012345',
            email_address='lakshmi@drafts.test', address='44 Church Street')
        api = self.client_for(self.owner)
        created = api.post(reverse('order-draft-list'),
                           {'payload': self.WIZARD, 'customer': str(customer.id)},
                           format='json')

        gone = api.delete(reverse('order-draft-detail', args=[created.data['id']]))

        self.assertEqual(gone.status_code, 204)
        self.assertEqual(OrderDraft.objects.count(), 0)
        # The client was on file before this draft and stays on file after it.
        self.assertTrue(Customer.objects.filter(pk=customer.pk).exists())


class StaleTabTests(DraftTestBase):
    """Two tabs on one draft is an ordinary thing to do."""

    def test_the_older_tab_cannot_overwrite_the_newer_one(self):
        api = self.client_for(self.owner)
        created = api.post(reverse('order-draft-list'),
                           {'payload': self.WIZARD, 'current_step': 2}, format='json')
        draft_id, opened_version = created.data['id'], created.data['version']
        url = reverse('order-draft-detail', args=[draft_id])

        # Tab B saves. Tab A still holds the version it opened.
        newer = api.patch(url, {'payload': {**self.WIZARD, 'last_name': 'Iyer-Rao'},
                                'current_step': 3, 'version': opened_version},
                          format='json')
        self.assertEqual(newer.status_code, 200)

        stale = api.patch(url, {'payload': {**self.WIZARD, 'last_name': 'STALE'},
                                'current_step': 2, 'version': opened_version},
                          format='json')

        self.assertEqual(stale.status_code, 409)
        self.assertIn('changed somewhere else', stale.data['error'])
        # And the newer tab's work is exactly as it left it.
        current = api.get(url).data
        self.assertEqual(current['payload']['last_name'], 'Iyer-Rao')
        self.assertEqual(current['current_step'], 3)

    def test_a_save_that_carries_the_current_version_is_accepted(self):
        api = self.client_for(self.owner)
        created = api.post(reverse('order-draft-list'),
                           {'payload': self.WIZARD}, format='json')
        url = reverse('order-draft-detail', args=[created.data['id']])
        first = api.patch(url, {'payload': self.WIZARD, 'current_step': 2,
                                'version': created.data['version']}, format='json')
        self.assertEqual(first.status_code, 200)
        second = api.patch(url, {'payload': self.WIZARD, 'current_step': 3,
                                 'version': first.data['version']}, format='json')
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data['current_step'], 3)


class ADraftIsNotAnOrderTests(DraftTestBase):
    """The half that matters now that transitions and stock are enforced."""

    def setUp(self):
        super().setUp()
        api = self.client_for(self.owner)
        api.post(reverse('order-draft-list'),
                 {'payload': self.WIZARD, 'current_step': 4}, format='json')
        self.assertEqual(OrderDraft.objects.count(), 1)

    def test_a_draft_creates_no_order_row(self):
        self.assertEqual(Order.objects.count(), 0)

    def test_a_draft_creates_no_customer(self):
        """The wizard used to POST the client at step one.

        Abandoning at step four then left a customer nobody had asked for, with
        no order attached and no route back to the work.
        """
        self.assertEqual(Customer.objects.count(), 0)

    def test_a_draft_creates_no_production_stages(self):
        self.assertEqual(OrderStage.objects.count(), 0)

    def test_a_draft_reserves_no_material_and_moves_no_stock(self):
        """The sharp edge. Materials follow production now."""
        self.brocade.refresh_from_db()
        self.assertEqual(self.brocade.current_stock, Decimal('25.000'))
        self.assertEqual(self.brocade.reserved_stock, Decimal('0.000'))
        self.assertEqual(OrderMaterialPlan.objects.count(), 0)
        self.assertFalse(
            StockMovement.objects.exclude(
                movement_type=StockMovement.Type.STOCK_IN).exists())

    def test_a_draft_messages_no_customer(self):
        self.assertEqual(CustomerMessage.objects.count(), 0)

    def test_a_draft_is_invisible_to_every_order_reader(self):
        """Dashboards, tracking, analytics and invoices all read orders.

        None of them can see a draft, because none of them know the model
        exists -- which is the whole reason it is a separate model rather than
        a flag on Order. Asserted against the queryset they all share.
        """
        from domains.orders.repositories import OrderRepository
        self.assertEqual(OrderRepository.get_all().count(), 0)
        self.assertEqual(OrderRepository.summary_queryset().count(), 0)

    def test_a_draft_does_not_count_as_revenue(self):
        api = self.client_for(self.owner)
        dashboard = api.get(reverse('dashboard'))
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.data['stats']['total_orders'], 0)
        self.assertEqual(dashboard.data['stats']['revenue'], 0)


class ConfirmTests(DraftTestBase):
    """One door from draft to order, and it closes behind you."""

    def test_confirming_creates_the_client_and_consumes_the_draft(self):
        draft = drafts.save_draft(self.owner, self.WIZARD, current_step=6)

        def create_order(d):
            customer = drafts.customer_for(d, d.payload)
            return Order.objects.create(
                order_id='T2B-CONFIRMED', customer=customer,
                total_amount=Decimal('1000'))

        order = drafts.confirm(self.owner, draft.id, create_order=create_order)

        self.assertEqual(order.order_id, 'T2B-CONFIRMED')
        self.assertEqual(order.customer.first_name, 'Lakshmi')
        self.assertEqual(OrderDraft.objects.count(), 0, 'the draft is spent')

    def test_a_failure_while_confirming_leaves_the_draft_intact(self):
        """Losing the order is recoverable. Losing the draft is not."""
        draft = drafts.save_draft(self.owner, self.WIZARD, current_step=6)

        def explode(d):
            raise RuntimeError('order creation failed')

        with self.assertRaises(RuntimeError):
            drafts.confirm(self.owner, draft.id, create_order=explode)

        self.assertEqual(OrderDraft.objects.count(), 1)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Customer.objects.count(), 0)

    def test_an_existing_client_is_reused_rather_than_duplicated(self):
        customer = Customer.objects.create(
            first_name='Lakshmi', last_name='Iyer', mobile_number='919845012345',
            email_address='lakshmi@drafts.test', address='44 Church Street')
        draft = drafts.save_draft(self.owner, self.WIZARD, customer=customer)

        resolved = drafts.customer_for(draft, draft.payload)

        self.assertEqual(resolved.pk, customer.pk)
        self.assertEqual(Customer.objects.count(), 1)


class AtomicConfirmOverHttpTests(DraftTestBase):
    """Draft -> atomic Confirm -> Order. No half-made state, ever."""

    def setUp(self):
        super().setUp()
        from apps.catalog.models import GarmentTemplate
        # The real seeded template, not a bare stand-in: its fields are what
        # the spec is validated against, so a hand-made one would let this test
        # pass on data the product would reject.
        self.template = GarmentTemplate.objects.get(key='blouse')
        self.tailor = Tailor.objects.create(
            name="Sunita Devi", specialty="Stitching", role="Tailor")
        self.api = self.client_for(self.owner)

    def a_draft(self, **overrides):
        payload = {
            'first_name': 'Lakshmi', 'last_name': 'Iyer',
            'mobile_number': '919845012345', 'email_address': 'lakshmi@drafts.test',
            'address': '44 Church Street', 'customer_type': 'Women',
            'measurements': {'bust': '36', 'waist': '30'},
            'prices': {'base': 5000},
            'staff': {'tailor_id': self.tailor.id},
            'payment': {'option': 'partial', 'advance': 1000},
            'garments': [{
                'template': str(self.template.id),
                'spec': {'blouse_type': 'princess'},
                'measurements': {'chest': '36'},
                'materials': [{'field_key': 'main_fabric',
                               'inventory_item': str(self.brocade.id),
                               'quantity': '2', 'source': 'STORE'}],
            }],
        }
        payload.update(overrides)
        created = self.api.post(reverse('order-draft-list'),
                                {'payload': payload, 'current_step': 6}, format='json')
        self.assertEqual(created.status_code, 201)
        return created.data['id']

    def test_confirming_builds_the_whole_order_in_one_go(self):
        draft_id = self.a_draft()
        response = self.api.post(reverse('order-draft-confirm', args=[draft_id]))

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(OrderDraft.objects.count(), 0)

        order = Order.objects.get()
        self.assertEqual(order.stages.count(), 15, 'production stages exist now')
        self.assertEqual(order.garment_jobs.count(), 1)
        job = order.garment_jobs.get()
        # The material line the inventory lifecycle needs -- with a quantity.
        self.assertEqual(job.materials.count(), 1)
        self.assertEqual(job.materials.get().quantity, Decimal('2.000'))
        self.assertEqual(job.measurements['chest'], '36')

    def test_the_material_lifecycle_only_begins_after_confirmation(self):
        draft_id = self.a_draft()
        self.brocade.refresh_from_db()
        self.assertEqual(self.brocade.reserved_stock, Decimal('0.000'))

        self.api.post(reverse('order-draft-confirm', args=[draft_id]))

        # Still nothing reserved: confirming books the order, production
        # commits the cloth. Fabric Confirmed is what reserves it.
        self.brocade.refresh_from_db()
        self.assertEqual(self.brocade.reserved_stock, Decimal('0.000'))
        self.assertEqual(OrderMaterialPlan.objects.count(), 0)

        # ...and now the lifecycle can run, because the lines exist.
        order = Order.objects.get()
        from domains.orders.services import OrderService
        for key in ('created', 'measurements_completed', 'fabric_confirmed'):
            OrderService.transition_order_stage(
                order=order, stage_key=key, new_status='COMPLETED', user=self.owner)
        self.brocade.refresh_from_db()
        self.assertEqual(self.brocade.reserved_stock, Decimal('2.000'))

    def test_confirming_twice_makes_one_order_not_two(self):
        """Double-click, network retry, or a refresh that re-fires the post."""
        draft_id = self.a_draft()

        first = self.api.post(reverse('order-draft-confirm', args=[draft_id]))
        second = self.api.post(reverse('order-draft-confirm', args=[draft_id]))
        third = self.api.post(reverse('order-draft-confirm', args=[draft_id]))

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(third.status_code, 409)
        self.assertIn('already been placed', second.data['error'])

        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(Order.objects.get().garment_jobs.count(), 1)
        self.assertEqual(OrderStage.objects.count(), 15)

    def test_a_failure_anywhere_in_confirm_leaves_the_draft_and_nothing_else(self):
        """The permanent regression: no partial order to clean up.

        A garment naming a template that no longer exists is one way in; the
        point is not that particular fault but that ANY fault mid-build takes
        the whole thing back with it.
        """
        # A negative price is refused by order creation, which is a fault
        # partway through the build -- after the client has been made and
        # before the garments are.
        draft_id = self.a_draft(prices={'base': -5000})

        response = self.api.post(reverse('order-draft-confirm', args=[draft_id]))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0, 'no half-made order')
        self.assertEqual(Customer.objects.count(), 0, 'no orphan client')
        self.assertEqual(OrderStage.objects.count(), 0)
        self.assertEqual(OrderDraft.objects.count(), 1, 'the work survives')
        self.brocade.refresh_from_db()
        self.assertEqual(self.brocade.reserved_stock, Decimal('0.000'))

    def test_an_existing_client_is_not_duplicated_by_confirming(self):
        customer = Customer.objects.create(
            first_name='Lakshmi', last_name='Iyer', mobile_number='919845012345',
            email_address='lakshmi@drafts.test', address='44 Church Street')
        created = self.api.post(
            reverse('order-draft-list'),
            {'payload': {'prices': {'base': 5000}, 'garments': []},
             'customer': str(customer.id), 'current_step': 6}, format='json')

        response = self.api.post(
            reverse('order-draft-confirm', args=[created.data['id']]))

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(Order.objects.get().customer_id, customer.id)


class TwoGarmentConfirmTests(DraftTestBase):
    """A two-garment order stays a two-garment order, all the way out.

    The acceptance run booked a blouse and a lehenga and the customer's
    confirmation message announced a blouse. The garment helper was right; it
    was asked too early -- create_order_for_customer notified from inside
    itself, before the confirm builder had created any garment jobs, so the
    helper correctly found none and fell back to the customer's single
    garment_type.

    These assert the garments by name rather than that the message merely
    mentions a garment, because "Garment: Blouse" passes the weaker test.
    """

    def setUp(self):
        super().setUp()
        from apps.catalog.models import GarmentTemplate
        self.blouse = GarmentTemplate.objects.get(key='blouse')
        self.lehenga = GarmentTemplate.objects.get(key='lehenga')
        self.tailor = Tailor.objects.create(
            name="Rekha Pillai", specialty="Stitching", role="Tailor")
        self.api = self.client_for(self.owner)

    def two_garment_draft(self):
        """The shape the wizard actually posts, not a hand-made one."""
        payload = {
            'first_name': 'Nandini', 'last_name': 'Krishnan',
            'mobile_number': '919845077788', 'email_address': 'nandini@drafts.test',
            'address': '31 Cunningham Road', 'customer_type': 'Women',
            'measurements': {'bust': '35', 'waist': '', 'hips': ''},
            'prices': {'base': 15000, 'embroidery': 7500},
            'staff': {'tailor_id': self.tailor.id},
            'payment': {'option': 'partial', 'advance': 12000},
            'delivery': {'method': 'Direct Pickup'},
            'garments': [
                {'key': 'blouse', 'template': str(self.blouse.id),
                 'template_key': 'blouse',
                 'spec': {'blouse_type': 'princess'},
                 'measurements': {'chest': '35', 'waist': '29'},
                 'values': {'delivery_date': '2026-10-10'},
                 'materials': [{'field_key': 'main_fabric',
                                'inventory_item': str(self.brocade.id),
                                'quantity': '1.5', 'source': 'STORE'}]},
                {'key': 'lehenga', 'template': str(self.lehenga.id),
                 'template_key': 'lehenga',
                 'spec': {'lehenga_type': 'a_line'},
                 'measurements': {'waist': '32', 'floor_length': '41'},
                 'values': {'delivery_date': '2026-10-10'},
                 'materials': [{'field_key': 'main_fabric',
                                'inventory_item': str(self.brocade.id),
                                'quantity': '4.5', 'source': 'STORE'}]},
            ],
        }
        created = self.api.post(reverse('order-draft-list'),
                                {'payload': payload, 'current_step': 6}, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        return created.data['id']

    def test_the_customer_confirmation_names_both_garments(self):
        draft_id = self.two_garment_draft()

        response = self.api.post(reverse('order-draft-confirm', args=[draft_id]))
        self.assertEqual(response.status_code, 201, response.data)

        body = CustomerMessage.objects.get().body
        self.assertIn('Blouse', body)
        self.assertIn('Lehenga', body)
        self.assertIn('Garments: Blouse and Lehenga', body)
        # The precise failure: the singular line naming only the first dress.
        self.assertNotIn('Garment: Blouse\n', body)

    def test_the_notification_is_not_sent_before_the_garments_exist(self):
        """Ordering, asserted directly rather than through its symptom."""
        draft_id = self.two_garment_draft()
        self.assertEqual(CustomerMessage.objects.count(), 0)

        self.api.post(reverse('order-draft-confirm', args=[draft_id]))

        order = Order.objects.get()
        message = CustomerMessage.objects.get()
        self.assertEqual(order.garment_jobs.count(), 2,
                         'both garments are on the order')
        self.assertEqual(message.order_id, order.id)
        # The message describes an order that was already whole when it was written.
        self.assertIn('Lehenga', message.body)

    def test_both_garments_survive_confirm_with_their_own_measurements(self):
        draft_id = self.two_garment_draft()
        self.api.post(reverse('order-draft-confirm', args=[draft_id]))

        jobs = {j.template.name: j for j in Order.objects.get().garment_jobs.all()}
        self.assertEqual(set(jobs), {'Blouse', 'Lehenga'})
        self.assertEqual(jobs['Blouse'].measurements['waist'], '29')
        self.assertEqual(jobs['Lehenga'].measurements['waist'], '32',
                         "neither garment's waist may overwrite the other's")

    def test_one_material_across_two_garments_stays_two_attributed_lines(self):
        draft_id = self.two_garment_draft()
        self.api.post(reverse('order-draft-confirm', args=[draft_id]))

        order = Order.objects.get()
        lines = [m for job in order.garment_jobs.all() for m in job.materials.all()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(sum(m.quantity for m in lines), Decimal('6.000'))
        self.assertEqual(len({m.job_id for m in lines}), 2)

    def test_the_order_serialiser_names_both_garments_for_every_screen(self):
        """Step-5 and step-6 summaries, the invoice and the dashboards all
        read this, so it is the one assertion that covers them together."""
        draft_id = self.two_garment_draft()
        response = self.api.post(reverse('order-draft-confirm', args=[draft_id]))

        self.assertEqual(response.data['garments'], ['Blouse', 'Lehenga'])
        self.assertEqual(response.data['garment_label'], 'Blouse and Lehenga')
