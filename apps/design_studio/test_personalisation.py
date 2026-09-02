"""Personalising a design for an order that does not exist yet.

Design Studio was built when the wizard POSTed the customer at step one, so
every entry point is customer-shaped. Drafts deliberately ended that -- an
abandoned order must not leave a half-made customer behind -- and the studio
never moved with them: a new-customer order reached step three, found
`customerId === null`, and rendered a blank silent screen.

The fix is NOT a second customer-less code path. It is one Subject with two
constructors (see context.Subject), so build_context, the query generator, the
ranker and every provider go on seeing a single shape. These tests pin that
equivalence, the per-garment isolation the projection now carries, and the two
things a draft must never do: create a customer, or leak one.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.catalog.models import GarmentJob, GarmentTemplate
from apps.catalog.services import sync_global_templates
from crm_api.models import (
    BoutiqueSettings, Customer, FabricSelection, Measurement, Order, OrderDraft,
)
from domains.orders import drafts

from .context import build_context, subject_from_customer, subject_from_draft


class PersonalisationTestBase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@personal.test"
        tenant.name = "Personalisation Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        sync_global_templates()
        BoutiqueSettings.objects.get_or_create(id=1)
        self.owner = User.objects.create_user(
            username="owner@personal.test", email="owner@personal.test",
            password="ownerpass123")
        self.blouse = GarmentTemplate.objects.get(key='blouse')
        self.lehenga = GarmentTemplate.objects.get(key='lehenga')
        self.api = self.client_for(self.owner)

    def client_for(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Token {token.key}',
                        HTTP_X_TENANT_ID=self.tenant.schema_name)
        return api

    def new_customer_payload(self):
        """Exactly what the wizard stores: template ids AND keys, per garment."""
        return {
            'first_name': 'Deepa', 'last_name': 'Krishnan',
            'mobile_number': '919611022233', 'email_address': 'deepa@personal.test',
            'customer_type': 'Women', 'occasion': 'Wedding',
            'neckline_style': 'Sweetheart', 'sleeve_style': 'Cap',
            'measurements': {'bust': '38', 'waist': '28', 'hips': '40'},
            'garments': [
                {'key': 'blouse', 'template_key': 'blouse',
                 'template': str(self.blouse.id),
                 'spec': {'blouse_type': 'princess', 'sleeve_length': 'elbow',
                          'front_neck': 'Deep V'},
                 'measurements': {'chest': '36'}},
                {'key': 'lehenga', 'template_key': 'lehenga',
                 'template': str(self.lehenga.id),
                 'spec': {'lehenga_type': 'a_line', 'border': 'with_border'},
                 'measurements': {'waist': '32', 'floor_length': '41'}},
            ],
        }

    def a_draft(self, payload=None, customer=None):
        return drafts.save_draft(
            self.owner, payload or self.new_customer_payload(),
            customer=customer, current_step=3)

    def saved_customer(self):
        customer = Customer.objects.create(
            first_name="Lakshmi", last_name="Iyer", mobile_number="919845012345",
            customer_type="Women", garment_type="Lehenga", occasion="Bridal",
            neckline_style="Boat", sleeve_style="Full", silhouette="A-Line")
        Measurement.objects.create(customer=customer, bust=Decimal('36'),
                                   waist=Decimal('30'), hips=Decimal('38'))
        FabricSelection.objects.create(customer=customer, fabric_name="Maroon Silk",
                                       fabric_price=Decimal('4000'))
        return customer


class SubjectEquivalenceTests(PersonalisationTestBase):
    """One shape, two sources -- the whole point of the architecture."""

    def test_a_draft_and_a_customer_produce_the_same_context_shape(self):
        draft_context = build_context(subject_from_draft(self.new_customer_payload()))
        saved_context = build_context(subject_from_customer(self.saved_customer()))
        self.assertEqual(set(draft_context.to_dict()), set(saved_context.to_dict()),
                         'downstream cannot be asked to tell the two apart')

    def test_a_draft_carries_the_typed_profile_and_measurements(self):
        context = build_context(subject_from_draft(self.new_customer_payload()))
        self.assertEqual(context.customer_name, 'Deepa Krishnan')
        self.assertEqual(context.gender, 'Women')
        self.assertEqual(context.measurements['bust'], '38')
        self.assertEqual(context.body_type, 'Hourglass')

    def test_a_draft_has_no_history_and_that_is_not_an_error(self):
        context = build_context(subject_from_draft(self.new_customer_payload()))
        self.assertEqual(context.favourite_colours, [])
        self.assertEqual(context.preferred_fabrics, [])
        self.assertEqual(context.previous_order_count, 0)

    def test_a_saved_customer_still_carries_real_history(self):
        context = build_context(subject_from_customer(self.saved_customer()))
        self.assertIn('Maroon Silk', context.preferred_fabrics)
        self.assertIn('Maroon', context.favourite_colours)

    def test_an_empty_draft_builds_rather_than_raising(self):
        context = build_context(subject_from_draft({}))
        self.assertEqual(context.customer_name, '')
        self.assertEqual(context.measurements, {})


class PerGarmentContextTests(PersonalisationTestBase):
    """Two dresses, one customer: only the spec tells them apart."""

    def _context_for(self, garment_key, draft_id):
        response = self.api.get(reverse('design-context'),
                                {'draft_id': str(draft_id), 'garment_key': garment_key})
        self.assertEqual(response.status_code, 200, response.data)
        return response.data['context']

    def test_each_garment_gets_its_own_context(self):
        draft = self.a_draft()
        blouse = self._context_for('blouse', draft.id)
        lehenga = self._context_for('lehenga', draft.id)

        self.assertEqual(blouse['garment_type'], 'blouse')
        self.assertEqual(lehenga['garment_type'], 'lehenga')
        self.assertNotEqual(blouse['style_preferences'], lehenga['style_preferences'])

    def test_a_garments_own_spec_beats_the_shared_customer_default(self):
        # Both garments inherit neckline "Sweetheart" from the one profile
        # behind them. A blouse declares a neck (front_neck) and must override
        # it; a lehenga's template has no neck field at all, so it keeps the
        # customer's -- and is distinguished instead by its own vocabulary,
        # `border`. Each garment personalises off what it actually declares.
        draft = self.a_draft()
        blouse = self._context_for('blouse', draft.id)
        lehenga = self._context_for('lehenga', draft.id)

        self.assertEqual(blouse['style_preferences']['neckline'], 'Deep V')
        self.assertEqual(blouse['style_preferences']['sleeve'], 'elbow')
        self.assertEqual(lehenga['style_preferences']['neckline'], 'Sweetheart')
        self.assertEqual(lehenga['style_preferences']['silhouette'], 'a_line')
        self.assertEqual(blouse['style_preferences']['silhouette'], 'princess')

    def test_garment_measurements_override_the_standing_ones(self):
        draft = self.a_draft()
        lehenga = self._context_for('lehenga', draft.id)
        # The customer's standing waist is 28; this lehenga is cut to 32.
        self.assertEqual(lehenga['measurements']['waist'], '32')
        self.assertEqual(lehenga['measurements']['floor_length'], '41')

    def test_changing_one_garment_does_not_move_the_other(self):
        draft = self.a_draft()
        before = self._context_for('lehenga', draft.id)

        payload = dict(self.new_customer_payload())
        payload['garments'] = [
            {**payload['garments'][0],
             'spec': {'blouse_type': 'katori', 'front_neck': 'Halter'}},
            payload['garments'][1],
        ]
        drafts.save_draft(self.owner, payload, draft_id=draft.id, current_step=3)

        after = self._context_for('lehenga', draft.id)
        self.assertEqual(before, after, "the lehenga's context is its own")
        self.assertEqual(self._context_for('blouse', draft.id)
                         ['style_preferences']['neckline'], 'Halter')

    def test_an_unknown_garment_is_refused_rather_than_guessed(self):
        draft = self.a_draft()
        response = self.api.get(reverse('design-context'),
                                {'draft_id': str(draft.id), 'garment_key': 'sherwani'})
        self.assertEqual(response.status_code, 400)

    def test_a_single_garment_draft_needs_no_key(self):
        payload = dict(self.new_customer_payload())
        payload['garments'] = [payload['garments'][0]]
        draft = self.a_draft(payload)
        response = self.api.get(reverse('design-context'), {'draft_id': str(draft.id)})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['context']['garment_type'], 'blouse')


class NoOrphanCustomerTests(PersonalisationTestBase):
    """Personalising must create nothing."""

    def test_personalising_a_draft_creates_no_customer_or_order(self):
        draft = self.a_draft()
        before = (Customer.objects.count(), Order.objects.count())

        self.api.get(reverse('design-context'),
                     {'draft_id': str(draft.id), 'garment_key': 'blouse'})
        self.api.post(reverse('design-discover'),
                      {'draft_id': str(draft.id), 'garment_key': 'lehenga'},
                      format='json')

        self.assertEqual((Customer.objects.count(), Order.objects.count()), before)
        self.assertEqual(Customer.objects.count(), 0, 'no orphan customer, ever')

    def test_personalising_creates_no_board_stage_or_message(self):
        from crm_api.models import CustomerMessage, OrderStage
        from apps.inventory.models import OrderMaterialPlan, StockMovement
        from .models import DesignBoard
        draft = self.a_draft()

        self.api.post(reverse('design-discover'),
                      {'draft_id': str(draft.id), 'garment_key': 'blouse'},
                      format='json')

        for model in (DesignBoard, OrderStage, OrderMaterialPlan, StockMovement,
                      CustomerMessage):
            self.assertEqual(model.objects.count(), 0,
                             f'{model.__name__} must not exist before Confirm')

    def test_the_draft_is_not_mutated_by_being_personalised(self):
        draft = self.a_draft()
        version, payload = draft.version, draft.payload
        self.api.get(reverse('design-context'),
                     {'draft_id': str(draft.id), 'garment_key': 'blouse'})
        draft.refresh_from_db()
        self.assertEqual(draft.version, version)
        self.assertEqual(draft.payload, payload)


class DraftOwnershipTests(PersonalisationTestBase):
    """A draft is personal until it becomes an order."""

    def test_another_owners_draft_is_not_readable(self):
        draft = self.a_draft()
        intruder = User.objects.create_user(
            username="other@personal.test", email="other@personal.test",
            password="otherpass123")
        response = self.client_for(intruder).get(
            reverse('design-context'), {'draft_id': str(draft.id)})
        # Refused, and without confirming the draft exists.
        self.assertIn(response.status_code, (400, 403, 404))
        self.assertNotIn('Deepa', str(response.data))

    def test_neither_source_named_browses_anonymously(self):
        # Naming neither used to be refused. The order wizard now opens on the
        # design step so a walk-in can pick a design and a fabric before giving
        # their name, so "no subject yet" is an ordinary request rather than a
        # malformed one -- it simply searches without personalising.
        response = self.api.post(reverse('design-discover'), {}, format='json')
        self.assertEqual(response.status_code, 200)

        # The point of the old rule was that nobody could probe the endpoint for
        # someone else's details. That still holds: an anonymous search carries
        # no customer, so there is no profile in the response to leak. Naming a
        # draft that is not yours is still refused, above.
        self.assertNotIn('Deepa', str(response.data))
        self.assertEqual(response.data['context'].get('customer_id', ''), '')


class ReturningCustomerTests(PersonalisationTestBase):
    """A draft for someone who already exists still gets their history."""

    def test_a_draft_linked_to_a_customer_uses_the_saved_profile(self):
        customer = self.saved_customer()
        draft = self.a_draft(customer=customer)

        response = self.api.get(reverse('design-context'),
                                {'draft_id': str(draft.id), 'garment_key': 'blouse'})
        self.assertEqual(response.status_code, 200, response.data)
        context = response.data['context']
        self.assertEqual(context['customer_id'], str(customer.id))
        self.assertIn('Maroon Silk', context['preferred_fabrics'])
        # And the garment still wins on style.
        self.assertEqual(context['style_preferences']['neckline'], 'Deep V')

    def test_personalising_an_existing_customer_creates_no_duplicate(self):
        customer = self.saved_customer()
        draft = self.a_draft(customer=customer)
        self.api.get(reverse('design-context'), {'draft_id': str(draft.id)})
        self.assertEqual(Customer.objects.count(), 1)


class PostConfirmContextTests(PersonalisationTestBase):
    """After Confirm the persisted garment job is canonical, not the draft."""

    def _confirm(self, draft_id):
        return self.api.post(reverse('order-draft-confirm', args=[draft_id]))

    def test_a_confirmed_garment_job_serves_its_own_context(self):
        draft = self.a_draft()
        response = self._confirm(draft.id)
        self.assertEqual(response.status_code, 201, response.data)

        order = Order.objects.get()
        jobs = {j.template.key: j for j in order.garment_jobs.all()}
        self.assertEqual(len(jobs), 2)

        for key, style_key, expected in (('blouse', 'neckline', 'Deep V'),
                                         ('lehenga', 'silhouette', 'a_line')):
            context = self.api.get(reverse('design-context'), {
                'customer_id': str(order.customer_id),
                'garment_key': str(jobs[key].id)}).data['context']
            self.assertEqual(context['garment_type'], key)
            self.assertEqual(context['style_preferences'][style_key], expected,
                             'the persisted job now serves its own context')

    def test_the_draft_is_spent_and_the_customer_now_exists(self):
        draft = self.a_draft()
        self._confirm(draft.id)
        self.assertEqual(OrderDraft.objects.count(), 0)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(Customer.objects.get().first_name, 'Deepa')

    def test_a_garment_job_from_another_customer_is_refused(self):
        draft = self.a_draft()
        self._confirm(draft.id)
        job = GarmentJob.objects.first()
        stranger = self.saved_customer()
        response = self.api.get(reverse('design-context'), {
            'customer_id': str(stranger.id), 'garment_key': str(job.id)})
        self.assertEqual(response.status_code, 400,
                         "one customer's garment must not personalise another's")


class DraftPersistenceTests(PersonalisationTestBase):
    """Save, refresh, resume -- personalisation survives because the draft does."""

    def test_context_is_identical_after_a_fresh_client_reads_the_draft(self):
        draft = self.a_draft()
        first = self.api.get(reverse('design-context'),
                             {'draft_id': str(draft.id), 'garment_key': 'blouse'}).data

        reopened = self.client_for(self.owner).get(
            reverse('design-context'),
            {'draft_id': str(draft.id), 'garment_key': 'blouse'}).data
        self.assertEqual(first['context'], reopened['context'])

    def test_edits_to_the_draft_reach_the_context(self):
        draft = self.a_draft()
        payload = dict(self.new_customer_payload())
        payload['measurements'] = {'bust': '40', 'waist': '30', 'hips': '42'}
        drafts.save_draft(self.owner, payload, draft_id=draft.id, current_step=3)

        context = self.api.get(reverse('design-context'),
                               {'draft_id': str(draft.id)}).data['context']
        self.assertEqual(context['measurements']['bust'], '40')


class SelectionSurvivesConfirmTests(PersonalisationTestBase):
    """A shortlist chosen before the customer existed lands on the right dress."""

    def _payload_with_designs(self):
        payload = self.new_customer_payload()
        payload['garments'][0]['design'] = {'items': [{
            'source': 'catalogue', 'source_ref': 'blouse-ref-1',
            'title': 'Princess Cut Blouse', 'image_url': 'https://x.test/b.jpg',
            'is_selected': True, 'match_score': 88,
        }]}
        payload['garments'][1]['design'] = {'items': [{
            'source': 'catalogue', 'source_ref': 'lehenga-ref-1',
            'title': 'A-Line Lehenga', 'image_url': 'https://x.test/l.jpg',
            'is_selected': True, 'match_score': 91,
        }]}
        return payload

    def test_each_garments_selection_lands_on_its_own_job(self):
        from .models import DesignBoard, DesignBoardItem
        draft = self.a_draft(self._payload_with_designs())
        response = self.api.post(reverse('order-draft-confirm', args=[draft.id]))
        self.assertEqual(response.status_code, 201, response.data)

        order = Order.objects.get()
        self.assertEqual(DesignBoard.objects.count(), 1, 'one board, as before')
        board = DesignBoard.objects.get()
        self.assertEqual(board.order_id, order.id)
        self.assertEqual(board.customer_id, order.customer_id)

        by_garment = {i.garment_job.template.key: i for i in
                      DesignBoardItem.objects.select_related('garment_job__template')}
        self.assertEqual(by_garment['blouse'].title, 'Princess Cut Blouse')
        self.assertEqual(by_garment['lehenga'].title, 'A-Line Lehenga')

    def test_both_garments_keep_their_own_selection(self):
        # The old one-selection-per-board rule would have let the second
        # garment's choice unpick the first's.
        from .models import DesignBoardItem
        draft = self.a_draft(self._payload_with_designs())
        self.api.post(reverse('order-draft-confirm', args=[draft.id]))
        selected = DesignBoardItem.objects.filter(is_selected=True)
        self.assertEqual(selected.count(), 2)
        self.assertEqual({i.garment_job.template.key for i in selected},
                         {'blouse', 'lehenga'})

    def test_a_confirm_with_no_shortlist_makes_no_board(self):
        draft = self.a_draft()
        self.api.post(reverse('order-draft-confirm', args=[draft.id]))
        from .models import DesignBoard
        self.assertEqual(DesignBoard.objects.count(), 0,
                         'an order nobody shortlisted for has no board')

    def test_confirm_retry_does_not_duplicate_the_board(self):
        from .models import DesignBoard, DesignBoardItem
        draft = self.a_draft(self._payload_with_designs())
        first = self.api.post(reverse('order-draft-confirm', args=[draft.id]))
        self.assertEqual(first.status_code, 201)
        counts = (DesignBoard.objects.count(), DesignBoardItem.objects.count())

        retry = self.api.post(reverse('order-draft-confirm', args=[draft.id]))
        self.assertEqual(retry.status_code, 409)
        self.assertEqual((DesignBoard.objects.count(), DesignBoardItem.objects.count()),
                         counts)


class PersonalisationPermissionTests(PersonalisationTestBase):
    """Adding a draft source must not widen who may personalise."""

    def _designer_client(self):
        from .models import Designer
        user = User.objects.create_user(
            username="priya@personal.test", email="priya@personal.test",
            password="designerpass123")
        Designer.objects.create(name="Priya Nair", email=user.email, user=user)
        return self.client_for(user)

    def _tailor_client(self):
        from crm_api.models import Tailor
        user = User.objects.create_user(
            username="stitcher@personal.test", email="stitcher@personal.test",
            password="tailorpass123")
        Tailor.objects.create(name="Sunita", specialty="Bridal", role="Tailor", user=user)
        return self.client_for(user)

    def test_a_designer_still_cannot_run_discovery(self):
        # OwnerOnly on the discovery endpoints predates P1.4 and stays. A
        # designer's window onto an order is the assignment projection built in
        # P1.1 -- spec, measurements and brief, no customer identity -- not this.
        draft = self.a_draft()
        client = self._designer_client()
        self.assertEqual(
            client.get(reverse('design-context'), {'draft_id': str(draft.id)}).status_code,
            403)
        self.assertEqual(
            client.post(reverse('design-discover'),
                        {'draft_id': str(draft.id)}, format='json').status_code,
            403)

    def test_a_tailor_cannot_personalise_either(self):
        draft = self.a_draft()
        client = self._tailor_client()
        self.assertEqual(
            client.get(reverse('design-context'), {'draft_id': str(draft.id)}).status_code,
            403)

    def test_the_draft_source_did_not_open_an_anonymous_door(self):
        draft = self.a_draft()
        anonymous = APIClient()
        anonymous.credentials(HTTP_X_TENANT_ID=self.tenant.schema_name)
        self.assertIn(
            anonymous.get(reverse('design-context'),
                          {'draft_id': str(draft.id)}).status_code,
            (401, 403))
