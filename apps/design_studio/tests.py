"""AI Design Studio.

Covers the three things the feature promises and could quietly get wrong: that
recommendations are explained and stable, that the design a tailor sees is the
one the owner approved, and that the role split in the spec is actually
enforced rather than assumed by the UI.
"""

import shutil
import tempfile
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import override_settings
from django.db.utils import IntegrityError
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from rest_framework.test import APIClient

from crm_api.models import Customer, FabricSelection, Measurement, Order, Tailor

from .context import build_context
from .intelligence.rules import RuleBasedIntelligence
from .models import Collection, Designer, DesignAsset, DesignBoard, DesignBoardItem
from .providers.base import DesignCandidate
from .serializers import DesignAssetSerializer
from .providers.registry import source_status
from . import services


class StudioTestCase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@studio.test"
        tenant.name = "Studio Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        from django.db import connection
        connection.set_tenant(self.tenant)

        self.owner = User.objects.create_user(
            username="owner@studio.test", email="owner@studio.test", password="pass12345")

        self.customer = Customer.objects.create(
            first_name="Ananya", last_name="Rao", mobile_number="9600001111",
            customer_type="Women", garment_type="Lehenga", occasion="Bridal",
            neckline_style="Sweetheart", sleeve_style="Half Sleeve",
            embellishments="Zari", pattern_style="Traditional", silhouette="A-Line",
        )
        Measurement.objects.create(
            customer=self.customer, bust=Decimal('38'), waist=Decimal('28'), hips=Decimal('40'))
        FabricSelection.objects.create(
            customer=self.customer, fabric_name="Maroon Silk", fabric_price=Decimal('4000'))

        # The catalogue is part of the design library now (migration 0007).
        self.design = DesignAsset.objects.create(
            title="Maroon Bridal Lehenga", garment_type="Lehenga",
            source=DesignAsset.SOURCE_CATALOGUE,
            attributes={'neckline_style': "Sweetheart", 'sleeve_style': "Half Sleeve"},
            image_url="https://example.test/lehenga.jpg", estimated_price=Decimal('35000'),
        )

        self.client = APIClient()
        self.client.credentials(HTTP_X_TENANT_ID=self.tenant.schema_name)
        self.client.force_authenticate(user=self.owner)

    def _staff_client(self, role, username):
        user = User.objects.create_user(username=username, email=username, password="pass12345")
        Tailor.objects.create(name=username, specialty="Bridal", role=role, user=user)
        client = APIClient()
        client.credentials(HTTP_X_TENANT_ID=self.tenant.schema_name)
        client.force_authenticate(user=user)
        return client

    def _board_with_selection(self):
        board = DesignBoard.objects.create(customer=self.customer, created_by=self.owner)
        item = DesignBoardItem.objects.create(
            board=board, source="catalogue", source_ref=str(self.design.id),
            title="Maroon Bridal Lehenga", image_url="https://example.test/lehenga.jpg")
        services.select_item(board, item)
        return board, item


class ContextEngineTests(StudioTestCase):
    def test_context_pulls_profile_measurements_and_history(self):
        context = build_context(self.customer, {'budget': '40000'})

        self.assertEqual(context.garment_type, "Lehenga")
        self.assertEqual(context.gender, "Women")
        self.assertEqual(context.measurements['bust'], 38.0)
        self.assertEqual(context.body_type, "Hourglass")
        self.assertEqual(context.budget, Decimal('40000'))
        self.assertIn("Maroon Silk", context.preferred_fabrics)
        self.assertIn("Maroon", context.favourite_colours)

    def test_in_flight_order_input_overrides_stored_defaults(self):
        # The wizard's current selection describes the order being placed now,
        # so it has to win over what the customer bought last time.
        context = build_context(self.customer, {'garment_type': 'Gown', 'occasion': 'Reception'})
        self.assertEqual(context.garment_type, "Gown")
        self.assertEqual(context.occasion, "Reception")

    def test_customer_without_measurements_still_builds(self):
        bare = Customer.objects.create(
            first_name="New", last_name="Client", mobile_number="9600002222")
        context = build_context(bare)
        self.assertEqual(context.measurements, {})
        self.assertEqual(context.body_type, "")


class IntelligenceTests(StudioTestCase):
    def setUp(self):
        super().setUp()
        self.engine = RuleBasedIntelligence()
        self.context = build_context(self.customer, {'budget': '40000'})

    def test_generated_queries_reflect_occasion_colour_and_garment(self):
        queries = self.engine.generate_queries(self.context)
        joined = " | ".join(queries).lower()
        self.assertIn("lehenga", joined)
        self.assertIn("bridal", joined)
        self.assertIn("maroon", joined)
        self.assertTrue(any("luxury" in q.lower() for q in queries))

    def test_manual_keywords_are_added(self):
        queries = self.engine.generate_queries(self.context, extra_keywords=["Peacock Motif"])
        self.assertIn("Peacock Motif", queries)

    def test_matching_design_outranks_unrelated_one_and_explains_why(self):
        strong = DesignCandidate(
            source="catalogue", source_ref="1", title="Maroon Bridal Lehenga",
            image_url="a.jpg", garment_type="Lehenga", occasion="Bridal",
            attributes={'neck_type': 'Sweetheart', 'sleeve': 'Half Sleeve', 'pattern': 'Traditional'},
            tags=["Bridal", "Maroon"], estimated_price=Decimal('35000'), popularity=80)
        weak = DesignCandidate(
            source="catalogue", source_ref="2", title="Cotton Office Kurti",
            image_url="b.jpg", garment_type="Kurti", estimated_price=Decimal('1200'))

        ranked = self.engine.rank([weak, strong], self.context)

        self.assertEqual(ranked[0].source_ref, "1")
        self.assertGreater(ranked[0].match_score, ranked[1].match_score)
        self.assertTrue(ranked[0].match_reasons)
        reasons = " ".join(ranked[0].match_reasons)
        self.assertIn("Lehenga", reasons)
        self.assertIn("budget", reasons.lower())

    def test_scores_are_bounded_and_repeatable(self):
        # A confidence score that drifts between identical searches makes the
        # gallery impossible to trust or to explain to a customer.
        candidates = [
            DesignCandidate(source="catalogue", source_ref=str(i), title=f"Lehenga {i}",
                            image_url="x.jpg", garment_type="Lehenga", occasion="Bridal",
                            estimated_price=Decimal('30000'), popularity=80)
            for i in range(5)
        ]
        first = [(c.source_ref, c.match_score) for c in self.engine.rank(list(candidates), self.context)]
        second = [(c.source_ref, c.match_score) for c in self.engine.rank(list(candidates), self.context)]

        self.assertEqual(first, second)
        for _, score in first:
            self.assertGreaterEqual(score, 0)
            self.assertLessEqual(score, 100)

    def test_signal_no_design_can_supply_does_not_depress_every_score(self):
        # Catalogue rows carry no occasion. Scoring them against a denominator
        # that includes the occasion weight capped a perfect catalogue match in
        # the forties and made the whole gallery read as a poor fit.
        perfect = DesignCandidate(
            source="catalogue", source_ref="1", title="Maroon Bridal Lehenga",
            image_url="a.jpg", garment_type="Lehenga",
            attributes={'neck_type': 'Sweetheart', 'sleeve': 'Half Sleeve', 'pattern': 'Traditional'},
            estimated_price=Decimal('30000'), popularity=80)

        ranked = self.engine.rank([perfect], self.context)

        self.assertGreaterEqual(ranked[0].match_score, 95)

    def test_a_design_that_fails_an_evaluable_signal_still_scores_lower(self):
        # The normalisation must not flatten real differences: here occasion is
        # judgeable for both candidates, so missing it has to cost.
        hit = DesignCandidate(
            source="library", source_ref="1", title="Lehenga", image_url="a.jpg",
            garment_type="Lehenga", occasion="Bridal", tags=["Bridal"])
        miss = DesignCandidate(
            source="library", source_ref="2", title="Lehenga", image_url="b.jpg",
            garment_type="Lehenga", occasion="Casual", tags=["Casual"])

        scores = {c.source_ref: c.match_score for c in self.engine.rank([hit, miss], self.context)}

        self.assertGreater(scores["1"], scores["2"])

    def test_over_budget_design_earns_no_budget_credit(self):
        cheap = DesignCandidate(source="catalogue", source_ref="1", title="Lehenga",
                                image_url="a.jpg", garment_type="Lehenga", occasion="Bridal",
                                estimated_price=Decimal('30000'))
        dear = DesignCandidate(source="catalogue", source_ref="2", title="Lehenga",
                               image_url="b.jpg", garment_type="Lehenga", occasion="Bridal",
                               estimated_price=Decimal('300000'))
        ranked = {c.source_ref: c.match_score for c in self.engine.rank([cheap, dear], self.context)}
        self.assertGreater(ranked["1"], ranked["2"])

    def test_analysis_infers_attributes_without_borrowing_customer_preferences(self):
        candidate = DesignCandidate(
            source="library", source_ref="1", title="Silk Boat Neck Gown",
            image_url="a.jpg", tags=["Zari", "Floral"])
        attributes = self.engine.analyse(candidate, self.context)

        self.assertEqual(attributes['fabric'], "Silk")
        self.assertEqual(attributes['neck_type'], "Boat Neck")
        self.assertEqual(attributes['embroidery'], "Zari")
        # The customer prefers a sweetheart neckline; the design does not have
        # one, and the analysis must not invent it.
        self.assertNotEqual(attributes['neck_type'], "Sweetheart")
        self.assertEqual(attributes['sleeve'], "")


class DiscoveryTests(StudioTestCase):
    def test_discovery_returns_ranked_catalogue_results(self):
        outcome = services.discover(self.customer, {'budget': '40000'})

        self.assertTrue(outcome['queries'])
        self.assertTrue(outcome['results'])
        titles = [c.title for c in outcome['results']]
        self.assertIn("Maroon Bridal Lehenga", titles)
        self.assertTrue(all(c.attributes for c in outcome['results']))

    def test_a_rejected_design_is_not_offered_again(self):
        """Archiving is how an owner rejects a design. Discovery used to read
        every row regardless of status, so a rejected design came straight back
        into the gallery, could be shortlisted onto a board and approved, and
        reached the tailor as the garment to stitch.
        """
        self.design.status = DesignAsset.Status.ARCHIVED
        self.design.save(update_fields=['status'])

        outcome = services.discover(self.customer, {'budget': '40000'})

        self.assertNotIn("Maroon Bridal Lehenga", [c.title for c in outcome['results']])

    def test_a_design_awaiting_approval_is_not_offered_either(self):
        """PENDING means a Master uploaded it and the owner has not reviewed
        it. Offering it for selection would route around the approval queue.
        """
        self.design.status = DesignAsset.Status.PENDING
        self.design.save(update_fields=['status'])

        outcome = services.discover(self.customer, {'budget': '40000'})

        self.assertNotIn("Maroon Bridal Lehenga", [c.title for c in outcome['results']])

    def test_a_failing_source_does_not_empty_the_gallery(self):
        from .providers import registry

        class Broken:
            key, label, is_external = 'broken', 'Broken', False

            def available(self):
                return True

            def search(self, queries, context, limit=20):
                raise RuntimeError("upstream is down")

        original = registry._PROVIDERS
        registry._PROVIDERS = [Broken(), *original]
        try:
            outcome = services.discover(self.customer)
        finally:
            registry._PROVIDERS = original

        self.assertTrue(outcome['results'])

    def test_external_sources_report_unavailable_without_credentials(self):
        statuses = {s['key']: s for s in source_status()}
        self.assertFalse(statuses['pinterest']['available'])
        self.assertFalse(statuses['google']['available'])
        self.assertTrue(statuses['catalogue']['available'])

    def test_discover_endpoint(self):
        response = self.client.post(reverse('design-discover'), {
            'customer_id': str(self.customer.id),
            'garment_type': 'Lehenga',
            'occasion': 'Bridal',
            'budget': '40000',
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['results'])
        self.assertTrue(response.data['queries'])
        self.assertTrue(response.data['results'][0]['match_reasons'])

    def test_context_endpoint(self):
        response = self.client.get(reverse('design-context'), {'customer_id': str(self.customer.id)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['context']['garment_type'], "Lehenga")
        self.assertTrue(response.data['suggested_queries'])


class BoardTests(StudioTestCase):
    def test_selecting_a_second_design_replaces_the_first(self):
        board, first = self._board_with_selection()
        second = DesignBoardItem.objects.create(
            board=board, source="catalogue", source_ref="99", title="Alternate")

        services.select_item(board, second)

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_selected)
        self.assertTrue(second.is_selected)
        self.assertEqual(board.items.filter(is_selected=True).count(), 1)

    def test_board_cannot_be_approved_without_a_selection(self):
        board = DesignBoard.objects.create(customer=self.customer)
        with self.assertRaises(ValueError):
            services.approve_board(board, self.owner)

    def test_unapproved_board_cannot_be_saved_to_an_order(self):
        board, _ = self._board_with_selection()
        order = Order.objects.create(order_id="T2B-DS-0001", customer=self.customer)
        with self.assertRaises(ValueError):
            services.save_to_order(board, order)

    def test_approved_board_saves_to_order_with_full_specification(self):
        board, item = self._board_with_selection()
        item.attributes = {'fabric': 'Silk', 'colour': 'Maroon'}
        item.tailor_instructions = "Reduce the border to two inches."
        item.save()
        services.approve_board(board, self.owner)
        order = Order.objects.create(order_id="T2B-DS-0002", customer=self.customer)

        services.save_to_order(board, order)

        order.refresh_from_db()
        attached = order.design_board
        self.assertEqual(attached.pk, board.pk)
        self.assertEqual(attached.selected_item.attributes['fabric'], "Silk")
        self.assertEqual(attached.selected_item.tailor_instructions,
                         "Reduce the border to two inches.")

    def test_saving_to_an_order_credits_the_library_design(self):
        # The library's "most ordered" sort and a designer's own performance
        # count on this: a dress does not silently stop being creditable to the
        # design it came from once the customer says yes.
        self.assertEqual(self.design.order_count, 0)
        board, _ = self._board_with_selection()
        services.approve_board(board, self.owner)
        order = Order.objects.create(order_id="T2B-DS-CREDIT", customer=self.customer)

        services.save_to_order(board, order)

        self.design.refresh_from_db()
        self.assertEqual(self.design.order_count, 1)

    def test_a_reference_with_no_matching_library_design_is_not_credited(self):
        # source_ref="7" here is not a DesignAsset id -- it is what a raw,
        # not-yet-imported external search result looks like. It must not be
        # mistaken for a UUID that happens to resolve to someone else's design.
        board = DesignBoard.objects.create(customer=self.customer)
        item = DesignBoardItem.objects.create(board=board, source="pinterest", source_ref="7")
        services.select_item(board, item)
        services.approve_board(board, self.owner)
        order = Order.objects.create(order_id="T2B-DS-NOCREDIT", customer=self.customer)

        services.save_to_order(board, order)  # must not raise

        self.design.refresh_from_db()
        self.assertEqual(self.design.order_count, 0)

    def test_a_second_board_cannot_hijack_an_order(self):
        first, _ = self._board_with_selection()
        services.approve_board(first, self.owner)
        order = Order.objects.create(order_id="T2B-DS-0003", customer=self.customer)
        services.save_to_order(first, order)

        second = DesignBoard.objects.create(customer=self.customer)
        item = DesignBoardItem.objects.create(board=second, source="catalogue", source_ref="7")
        services.select_item(second, item)
        services.approve_board(second, self.owner)

        with self.assertRaises(ValueError):
            services.save_to_order(second, order)

    def test_shortlist_and_approve_through_the_api(self):
        board_response = self.client.post(
            reverse('design-board-list'), {'customer': str(self.customer.id)}, format='json')
        self.assertEqual(board_response.status_code, 201)
        board_id = board_response.data['id']

        item_response = self.client.post(
            reverse('design-board-add-item', args=[board_id]),
            {'source': 'catalogue', 'source_ref': str(self.design.id),
             'title': 'Maroon Bridal Lehenga', 'image_url': 'https://example.test/lehenga.jpg',
             'match_score': 96, 'match_reasons': ['Trending bridal style']},
            format='json')
        self.assertEqual(item_response.status_code, 201)
        item_id = item_response.data['id']

        select = self.client.post(reverse('design-board-select-item', args=[board_id, item_id]))
        self.assertEqual(select.status_code, 200)

        approve = self.client.post(reverse('design-board-approve', args=[board_id]))
        self.assertEqual(approve.status_code, 200)
        self.assertEqual(approve.data['status'], DesignBoard.STATUS_APPROVED)
        self.assertEqual(approve.data['selected']['match_score'], 96)

    def test_select_response_shows_the_selection_in_its_items(self):
        # The board is loaded with items prefetched. Serialising that cached
        # list after the update sent back a board whose items all read
        # is_selected=false, so the gallery could not tell which design had
        # just been chosen and left the approve button disabled.
        board = DesignBoard.objects.create(customer=self.customer, created_by=self.owner)
        item = DesignBoardItem.objects.create(
            board=board, source="catalogue", source_ref="1", title="Chosen")

        response = self.client.post(reverse('design-board-select-item', args=[board.id, item.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['selected']['id'], str(item.id))
        selected_rows = [row for row in response.data['items'] if row['is_selected']]
        self.assertEqual(len(selected_rows), 1)
        self.assertEqual(selected_rows[0]['id'], str(item.id))

    def test_customisation_merges_into_attributes(self):
        board, item = self._board_with_selection()
        item.attributes = {'fabric': 'Silk', 'sleeve': 'Half Sleeve'}
        item.save()

        response = self.client.patch(
            reverse('design-board-customise-item', args=[board.id, item.id]),
            {'attributes': {'sleeve': 'Full Sleeve'}, 'tailor_instructions': 'Lengthen by 2 inches'},
            format='json')

        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.attributes['sleeve'], "Full Sleeve")
        self.assertEqual(item.attributes['fabric'], "Silk")
        self.assertEqual(item.tailor_instructions, "Lengthen by 2 inches")


class PermissionTests(StudioTestCase):
    def test_anonymous_caller_is_rejected(self):
        anonymous = APIClient()
        anonymous.credentials(HTTP_X_TENANT_ID=self.tenant.schema_name)
        for url in (reverse('design-board-list'), reverse('design-discover')):
            response = anonymous.get(url)
            self.assertIn(response.status_code, (401, 403))

    def test_staff_cannot_run_design_discovery(self):
        master = self._staff_client("Master", "master@studio.test")
        response = master.post(reverse('design-discover'),
                               {'customer_id': str(self.customer.id)}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_tailor_sees_only_approved_boards(self):
        draft, _ = self._board_with_selection()
        approved, _ = self._board_with_selection()
        services.approve_board(approved, self.owner)

        tailor = self._staff_client("Tailor", "tailor@studio.test")
        response = tailor.get(reverse('design-board-list'))

        self.assertEqual(response.status_code, 200)
        returned = {row['id'] for row in response.data}
        self.assertIn(str(approved.id), returned)
        self.assertNotIn(str(draft.id), returned)

    def test_tailor_brief_is_the_approved_design_and_its_instructions(self):
        board, item = self._board_with_selection()
        item.tailor_instructions = "Hand-finish the hem."
        item.save()
        services.approve_board(board, self.owner)

        tailor = self._staff_client("Tailor", "tailor2@studio.test")
        response = tailor.get(reverse('design-board-detail', args=[board.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['design']['tailor_instructions'], "Hand-finish the hem.")
        # The brief is the decision, not the deliberation.
        self.assertNotIn('items', response.data)

    def test_tailor_cannot_write(self):
        board, item = self._board_with_selection()
        services.approve_board(board, self.owner)
        tailor = self._staff_client("Tailor", "tailor3@studio.test")

        response = tailor.patch(
            reverse('design-board-production-notes', args=[board.id, item.id]),
            {'production_notes': "I will do it my way."}, format='json')

        self.assertEqual(response.status_code, 403)

    def test_master_can_add_production_notes_to_an_approved_design(self):
        board, item = self._board_with_selection()
        services.approve_board(board, self.owner)
        master = self._staff_client("Master", "master2@studio.test")

        response = master.patch(
            reverse('design-board-production-notes', args=[board.id, item.id]),
            {'production_notes': "Cut the lining separately."}, format='json')

        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.production_notes, "Cut the lining separately.")
        self.assertEqual(item.production_notes_by.name, "master2@studio.test")

    def test_master_cannot_annotate_a_design_that_is_not_approved_yet(self):
        board, item = self._board_with_selection()
        master = self._staff_client("Master", "master3@studio.test")

        response = master.patch(
            reverse('design-board-production-notes', args=[board.id, item.id]),
            {'production_notes': "Starting now."}, format='json')

        self.assertEqual(response.status_code, 400)


class DesignerAttributionTests(StudioTestCase):
    """Designers as credits, not accounts.

    The point of this step is that a portfolio is countable: every design a
    person contributed hangs off one row, however the credit was originally
    spelled or imported.
    """

    def _asset(self, title, designer='', **kw):
        return DesignAsset.objects.create(
            title=title, image_url=f"https://example.test/{title}.jpg",
            designer=designer, **kw)

    def test_a_designer_needs_no_login(self):
        designer = Designer.objects.create(name="Priya")
        self.assertIsNone(designer.user_id)
        self.assertIsNone(designer.staff_id)
        self.assertTrue(designer.is_active)

    def test_designs_count_towards_the_portfolio(self):
        priya = Designer.objects.create(name="Priya")
        self._asset("one", designer_ref=priya)
        self._asset("two", designer_ref=priya)
        self._asset("unattributed")
        self.assertEqual(priya.designs.count(), 2)

    def test_two_designers_cannot_share_a_name(self):
        Designer.objects.create(name="Priya")
        with self.assertRaises(IntegrityError):
            Designer.objects.create(name="Priya")

    def test_deleting_a_designer_keeps_the_designs(self):
        # A portfolio being removed must not take the boutique's library with it.
        priya = Designer.objects.create(name="Priya")
        asset = self._asset("kept", designer="Priya", designer_ref=priya)
        priya.delete()
        asset.refresh_from_db()
        self.assertIsNone(asset.designer_ref_id)
        self.assertEqual(asset.designer, "Priya")  # the credit survives

    def test_credited_name_falls_back_to_the_imported_text(self):
        imported = self._asset("pinterest-find", designer="Anita Rao")
        linked = self._asset("in-house", designer_ref=Designer.objects.create(name="Priya"))
        self.assertEqual(DesignAssetSerializer(imported).data['designer_name'], "Anita Rao")
        self.assertEqual(DesignAssetSerializer(linked).data['designer_name'], "Priya")

    def test_designer_list_reports_counts(self):
        priya = Designer.objects.create(name="Priya")
        self._asset("a", designer_ref=priya)
        self._asset("b", designer_ref=priya)
        Designer.objects.create(name="Ravi")

        response = self.client.get('/api/design-studio/designers/')
        self.assertEqual(response.status_code, 200)
        counts = {d['name']: d['design_count'] for d in response.data}
        self.assertEqual(counts, {"Priya": 2, "Ravi": 0})
        self.assertFalse(response.data[0]['has_login'])

    def test_portfolio_returns_only_that_designers_work(self):
        priya = Designer.objects.create(name="Priya")
        ravi = Designer.objects.create(name="Ravi")
        self._asset("hers", designer_ref=priya)
        self._asset("his", designer_ref=ravi)

        response = self.client.get(f'/api/design-studio/designers/{priya.id}/portfolio/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([d['title'] for d in response.data['designs']], ["hers"])
        self.assertEqual(response.data['designer']['design_count'], 1)

    def test_a_tailor_cannot_edit_the_designer_roster(self):
        tailor = self._staff_client('Tailor', 'tailor@studio.test')
        self.assertEqual(tailor.get('/api/design-studio/designers/').status_code, 200)
        created = tailor.post('/api/design-studio/designers/', {'name': 'Sneaky'}, format='json')
        self.assertEqual(created.status_code, 403)

    def test_the_owner_can_add_a_designer(self):
        """The counterpart to the 403 above, and the path the roster's own
        "Add designer" form posts to. Until that form existed nothing called
        this endpoint, so a boutique set up after the 0003 backfill had an
        empty roster it could never fill."""
        response = self.client.post(
            '/api/design-studio/designers/',
            {'name': 'Meera', 'email': 'meera@studio.test'}, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['name'], 'Meera')
        # Credit only: adding a designer must not hand out a login on its own.
        self.assertFalse(response.data['has_login'])
        self.assertTrue(Designer.objects.filter(name='Meera', user__isnull=True).exists())

    def test_a_designer_can_be_added_without_an_email(self):
        """Attribution comes first -- a name is the only thing required, and
        the address can arrive later when the Owner grants the login."""
        response = self.client.post(
            '/api/design-studio/designers/', {'name': 'Ravi'}, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['email'], '')


class DesignerBackfillTests(StudioTestCase):
    """The migration that turns existing free-text credits into rows."""

    def _run_backfill(self):
        from .migrations import __name__ as _  # noqa: F401
        from importlib import import_module
        module = import_module('apps.design_studio.migrations.0003_backfill_designers')
        # The migration works against historical models; the live ones are
        # compatible here because no field it touches has changed since.
        class Apps:
            @staticmethod
            def get_model(app_label, name):
                return {'Designer': Designer, 'DesignAsset': DesignAsset}[name]
        module.backfill(Apps, None)

    def test_variant_spellings_collapse_into_one_designer(self):
        for title, credit in [("a", "Priya"), ("b", "priya "), ("c", "PRIYA")]:
            DesignAsset.objects.create(
                title=title, image_url=f"https://example.test/{title}.jpg", designer=credit)

        self._run_backfill()

        self.assertEqual(Designer.objects.count(), 1)
        priya = Designer.objects.get()
        self.assertEqual(priya.name, "Priya")   # the earliest spelling wins
        self.assertEqual(priya.designs.count(), 3)

    def test_designs_with_no_credit_are_left_alone(self):
        anon = DesignAsset.objects.create(title="anon", image_url="https://example.test/anon.jpg")
        self._run_backfill()
        self.assertEqual(Designer.objects.count(), 0)
        anon.refresh_from_db()
        self.assertIsNone(anon.designer_ref_id)

    def test_running_it_twice_creates_nothing_extra(self):
        DesignAsset.objects.create(
            title="a", image_url="https://example.test/a.jpg", designer="Priya")
        self._run_backfill()
        self._run_backfill()
        self.assertEqual(Designer.objects.count(), 1)


class DesignLibraryTests(StudioTestCase):
    """Template linkage, tag filtering and the counters."""

    def setUp(self):
        super().setUp()
        from apps.catalog.services import sync_global_templates
        sync_global_templates()
        from apps.catalog.models import GarmentTemplate
        self.lehenga = GarmentTemplate.resolve('lehenga')
        self.blouse = GarmentTemplate.resolve('blouse')

    def _asset(self, title, **kw):
        return DesignAsset.objects.create(
            title=title, image_url=f"https://example.test/{title}.jpg", **kw)

    def test_filtering_by_garment_uses_the_template_not_a_string(self):
        self._asset("skirt", template=self.lehenga)
        self._asset("top", template=self.blouse)
        response = self.client.get('/api/design-studio/assets/?template=lehenga')
        self.assertEqual([d['title'] for d in response.data], ["skirt"])

    def test_tag_filters_use_the_order_forms_vocabulary(self):
        self._asset("elbow one", spec_tags={'sleeve_length': 'elbow'})
        self._asset("full one", spec_tags={'sleeve_length': 'full'})
        response = self.client.get('/api/design-studio/assets/?sleeve_length=elbow')
        self.assertEqual([d['title'] for d in response.data], ["elbow one"])

    def test_tag_filters_combine(self):
        self._asset("match", spec_tags={'sleeve_length': 'elbow', 'occasion': 'wedding'})
        self._asset("half match", spec_tags={'sleeve_length': 'elbow', 'occasion': 'party'})
        response = self.client.get(
            '/api/design-studio/assets/?sleeve_length=elbow&occasion=wedding')
        self.assertEqual([d['title'] for d in response.data], ["match"])

    def test_price_range_and_search(self):
        self._asset("cheap", estimated_price=Decimal('2000'))
        self._asset("dear", estimated_price=Decimal('9000'))
        # The fixture's catalogue design is also in the library, so assert on
        # membership rather than on the library being otherwise empty.
        response = self.client.get('/api/design-studio/assets/?price_min=5000')
        titles = [d['title'] for d in response.data]
        self.assertIn("dear", titles)
        self.assertNotIn("cheap", titles)
        response = self.client.get('/api/design-studio/assets/?search=chea')
        self.assertEqual([d['title'] for d in response.data], ["cheap"])

    def test_opening_a_design_counts_a_view(self):
        asset = self._asset("watched")
        self.assertEqual(asset.view_count, 0)
        self.client.get(f'/api/design-studio/assets/{asset.id}/')
        self.client.get(f'/api/design-studio/assets/{asset.id}/')
        asset.refresh_from_db()
        self.assertEqual(asset.view_count, 2)

    def test_listing_does_not_count_views(self):
        # Otherwise every gallery scroll inflates the "most viewed" leaderboard.
        asset = self._asset("listed")
        self.client.get('/api/design-studio/assets/')
        asset.refresh_from_db()
        self.assertEqual(asset.view_count, 0)

    def test_ordering_by_popularity(self):
        self._asset("quiet", view_count=1)
        self._asset("loud", view_count=99)
        response = self.client.get('/api/design-studio/assets/?ordering=most_viewed')
        self.assertEqual([d['title'] for d in response.data][0], "loud")

    def test_new_designs_are_active_and_boutique_visible(self):
        asset = self._asset("fresh")
        self.assertEqual(asset.status, DesignAsset.Status.ACTIVE)
        self.assertEqual(asset.visibility, DesignAsset.Visibility.BOUTIQUE)


class TemplateBackfillTests(StudioTestCase):
    """The migration that links designs to templates and tags them."""

    def setUp(self):
        super().setUp()
        from apps.catalog.services import sync_global_templates
        sync_global_templates()

    def _run(self):
        from importlib import import_module
        from apps.catalog.models import GarmentTemplate
        module = import_module('apps.design_studio.migrations.0005_backfill_template_tags')

        class Apps:
            @staticmethod
            def get_model(app_label, name):
                return {'GarmentTemplate': GarmentTemplate, 'DesignAsset': DesignAsset}[name]
        module.backfill(Apps, None)

    def test_garment_type_string_becomes_a_template_link(self):
        asset = DesignAsset.objects.create(
            title="a", image_url="https://example.test/a.jpg", garment_type="Lehenga")
        self._run()
        asset.refresh_from_db()
        self.assertIsNotNone(asset.template_id)
        self.assertEqual(asset.template.key, 'lehenga')

    def test_an_unrecognised_garment_is_left_unlinked(self):
        asset = DesignAsset.objects.create(
            title="b", image_url="https://example.test/b.jpg", garment_type="Poncho")
        self._run()
        asset.refresh_from_db()
        self.assertIsNone(asset.template_id)

    def test_only_values_the_order_form_offers_become_tags(self):
        asset = DesignAsset.objects.create(
            title="c", image_url="https://example.test/c.jpg", garment_type="Blouse",
            occasion="Wedding",
            attributes={'sleeve': 'Elbow', 'neck': 'Something Bespoke'})
        self._run()
        asset.refresh_from_db()
        # 'Elbow' and 'Wedding' are real options; the freehand neck is not, and
        # inventing a value for it would make the design unmatchable.
        self.assertEqual(asset.spec_tags, {'sleeve_length': 'elbow', 'occasion': 'wedding'})

    def test_existing_tags_are_not_overwritten(self):
        asset = DesignAsset.objects.create(
            title="d", image_url="https://example.test/d.jpg", garment_type="Blouse",
            occasion="Party", spec_tags={'sleeve_length': 'full'})
        self._run()
        asset.refresh_from_db()
        self.assertEqual(asset.spec_tags, {'sleeve_length': 'full'})


class DesignCategoryTests(StudioTestCase):
    """The library's section list."""

    def setUp(self):
        super().setUp()
        from apps.catalog.services import sync_global_templates
        sync_global_templates()
        from apps.catalog.models import GarmentTemplate
        self.lehenga = GarmentTemplate.resolve('lehenga')

    def test_counts_are_per_garment(self):
        for i in range(3):
            DesignAsset.objects.create(
                title=f"l{i}", image_url="https://example.test/l.jpg", template=self.lehenga)
        response = self.client.get('/api/design-studio/categories/')
        counts = {c['key']: c['count'] for c in response.data['categories']}
        self.assertEqual(counts['lehenga'], 3)
        self.assertEqual(counts['blouse'], 0)

    def test_every_garment_appears_even_with_nothing_in_it(self):
        # An empty category is information: it tells the owner what to fill.
        response = self.client.get('/api/design-studio/categories/')
        keys = {c['key'] for c in response.data['categories']}
        self.assertTrue({'saree', 'lehenga', 'churidar'} <= keys)

    def test_untagged_designs_are_still_reachable(self):
        # self.design from the fixture has no template; it must not vanish.
        response = self.client.get('/api/design-studio/categories/')
        categories = {c['key']: c['count'] for c in response.data['categories']}
        self.assertGreaterEqual(categories.get('', 0), 1)

    def test_total_matches_the_sum_of_the_sections(self):
        DesignAsset.objects.create(
            title="x", image_url="https://example.test/x.jpg", template=self.lehenga)
        response = self.client.get('/api/design-studio/categories/')
        self.assertEqual(
            response.data['total'],
            sum(c['count'] for c in response.data['categories']))

    def test_archived_designs_are_not_counted(self):
        DesignAsset.objects.create(
            title="gone", image_url="https://example.test/g.jpg", template=self.lehenga,
            status=DesignAsset.Status.ARCHIVED)
        response = self.client.get('/api/design-studio/categories/')
        counts = {c['key']: c['count'] for c in response.data['categories']}
        self.assertEqual(counts['lehenga'], 0)


class CollectionTests(StudioTestCase):
    """Collections, and the upload that files a design into one."""

    def setUp(self):
        super().setUp()
        from apps.catalog.services import sync_global_templates
        sync_global_templates()
        from apps.catalog.models import GarmentTemplate
        self.lehenga = GarmentTemplate.resolve('lehenga')
        self.priya = Designer.objects.create(name="Priya")

    def test_a_collection_belongs_to_a_designer(self):
        collection = Collection.objects.create(designer=self.priya, name="Bridal 2026")
        self.assertEqual(collection.designer, self.priya)
        self.assertEqual(list(self.priya.collections.all()), [collection])

    def test_two_designers_may_each_have_a_bridal_2026(self):
        ravi = Designer.objects.create(name="Ravi")
        Collection.objects.create(designer=self.priya, name="Bridal 2026")
        Collection.objects.create(designer=ravi, name="Bridal 2026")
        self.assertEqual(Collection.objects.filter(name="Bridal 2026").count(), 2)

    def test_one_designer_may_not_have_it_twice(self):
        Collection.objects.create(designer=self.priya, name="Bridal 2026")
        with self.assertRaises(IntegrityError):
            Collection.objects.create(designer=self.priya, name="Bridal 2026")

    def test_removing_a_collection_keeps_its_designs(self):
        # Unfiling a design must not delete the boutique's work.
        collection = Collection.objects.create(designer=self.priya, name="Summer")
        design = DesignAsset.objects.create(
            title="kept", image_url="https://example.test/k.jpg", collection=collection)
        collection.delete()
        design.refresh_from_db()
        self.assertIsNone(design.collection_id)

    def test_collection_list_reports_counts(self):
        collection = Collection.objects.create(designer=self.priya, name="Bridal 2026")
        for i in range(2):
            DesignAsset.objects.create(
                title=f"d{i}", image_url="https://example.test/d.jpg", collection=collection)
        response = self.client.get('/api/design-studio/collections/')
        self.assertEqual(response.status_code, 200)
        row = next(c for c in response.data if c['name'] == "Bridal 2026")
        self.assertEqual(row['design_count'], 2)
        self.assertEqual(row['designer_name'], "Priya")

    def test_library_filters_by_collection(self):
        collection = Collection.objects.create(designer=self.priya, name="Summer")
        DesignAsset.objects.create(
            title="in", image_url="https://example.test/i.jpg", collection=collection)
        DesignAsset.objects.create(title="out", image_url="https://example.test/o.jpg")
        response = self.client.get(f'/api/design-studio/assets/?collection={collection.id}')
        self.assertEqual([d['title'] for d in response.data], ["in"])


class DesignUploadTests(StudioTestCase):
    """The upload flow."""

    def setUp(self):
        super().setUp()

        # Storage goes to a temp directory, because media/ is tracked in git and
        # otherwise every run of the suite leaves uploaded fixtures in the repo.
        #
        # Enabled here rather than as a class decorator: TenantTestCase does not
        # run the class-level override machinery, so the decorator silently did
        # nothing and the files kept landing in the working tree. And STORAGES
        # has to be overridden alongside MEDIA_ROOT, because default_storage
        # caches its location the first time it is built.
        media_root = tempfile.mkdtemp(prefix='design-upload-test-')
        override = override_settings(
            MEDIA_ROOT=media_root,
            STORAGES={
                'default': {
                    'BACKEND': 'django.core.files.storage.FileSystemStorage',
                    'OPTIONS': {'location': media_root},
                },
                'staticfiles': {
                    'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
            },
        )
        override.enable()
        self.addCleanup(override.disable)
        self.addCleanup(shutil.rmtree, media_root, True)

        from apps.catalog.services import sync_global_templates
        sync_global_templates()
        from apps.catalog.models import GarmentTemplate
        self.lehenga = GarmentTemplate.resolve('lehenga')

    def _image(self, name='shot.jpg'):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile(name, b'\xff\xd8\xff\xdb-not-really-a-jpeg', content_type='image/jpeg')

    def test_uploading_stores_the_photograph_and_uses_it_as_the_cover(self):
        response = self.client.post('/api/design-studio/assets/', {
            'title': 'Hand embroidered lehenga',
            'template': str(self.lehenga.id),
            'images': self._image(),
        }, format='multipart')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIn('design_library/', response.data['image_url'])
        self.assertEqual(response.data['gallery'], [])

    def test_extra_photographs_become_the_gallery(self):
        response = self.client.post('/api/design-studio/assets/', {
            'title': 'Three views',
            'images': [self._image('a.jpg'), self._image('b.jpg'), self._image('c.jpg')],
        }, format='multipart')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(response.data['gallery']), 2)

    def test_a_photograph_too_large_to_buffer_in_memory_still_uploads(self):
        # Django keeps a small upload in memory as a BytesIO, but spills
        # anything over FILE_UPLOAD_MAX_MEMORY_SIZE to a TemporaryUploadedFile
        # wrapping an open file handle. The view used to run request.data.copy()
        # over that, and deep-copying a file handle raises
        # "TypeError: cannot pickle 'BufferedRandom' instances", so every upload
        # above the threshold returned a 500 before the view's own logic ran.
        #
        # The default threshold is 2.5MB and a photograph taken on a phone is
        # always larger, so this broke every real camera upload while the
        # kilobyte fixtures the tests above use stayed in memory and passed.
        # Lowering the threshold reproduces it without a multi-megabyte fixture.
        with override_settings(FILE_UPLOAD_MAX_MEMORY_SIZE=1):
            response = self.client.post('/api/design-studio/assets/', {
                'title': 'Straight off a phone camera',
                'template': str(self.lehenga.id),
                'images': self._image(),
            }, format='multipart')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIn('design_library/', response.data['image_url'])

    def test_an_upload_is_live_not_pending(self):
        # The approval queue does not exist yet. Creating PENDING rows before
        # there is a queue to clear them would hide every upload with no way to
        # get it back.
        response = self.client.post('/api/design-studio/assets/', {
            'title': 'Straight to the library',
            'image_url': 'https://example.test/x.jpg',
        }, format='json')
        self.assertEqual(response.data['status'], DesignAsset.Status.ACTIVE)

    def test_upload_carries_template_vocabulary_tags(self):
        response = self.client.post('/api/design-studio/assets/', {
            'title': 'Tagged on the way in',
            'image_url': 'https://example.test/t.jpg',
            'template': str(self.lehenga.id),
            'spec_tags': {'occasion': 'wedding', 'waist_finish': 'dori'},
            'difficulty': DesignAsset.Difficulty.COMPLEX,
            'stitch_hours': '18.5',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        found = self.client.get('/api/design-studio/assets/?occasion=wedding')
        self.assertIn('Tagged on the way in', [d['title'] for d in found.data])

    def test_a_posted_url_is_not_overwritten_by_an_upload(self):
        response = self.client.post('/api/design-studio/assets/', {
            'title': 'Imported, with a snapshot attached',
            'image_url': 'https://example.test/original.jpg',
            'images': self._image(),
        }, format='multipart')
        self.assertEqual(response.data['image_url'], 'https://example.test/original.jpg')


class ApprovalQueueTests(StudioTestCase):
    """The upload gate and the review action."""

    def setUp(self):
        super().setUp()
        from crm_api.models import BoutiqueSettings
        self.config, _ = BoutiqueSettings.objects.get_or_create(id=1)

    def test_approval_is_off_by_default(self):
        # A small team should not hit a queue with nobody on the other end.
        self.assertFalse(self.config.design_approval_required)
        response = self.client.post('/api/design-studio/assets/', {
            'title': 'Straight in', 'image_url': 'https://example.test/x.jpg',
        }, format='json')
        self.assertEqual(response.data['status'], DesignAsset.Status.ACTIVE)

    def test_the_owners_own_upload_skips_the_queue_even_when_it_is_on(self):
        self.config.design_approval_required = True
        self.config.save()
        response = self.client.post('/api/design-studio/assets/', {
            'title': 'Owner upload', 'image_url': 'https://example.test/o.jpg',
        }, format='json')
        self.assertEqual(response.data['status'], DesignAsset.Status.ACTIVE)

    def test_a_non_owners_upload_is_held_for_review_when_the_queue_is_on(self):
        self.config.design_approval_required = True
        self.config.save()
        tailor_client = self._staff_client('Tailor', 'queued@studio.test')
        response = tailor_client.post('/api/design-studio/assets/', {
            'title': 'Needs a look', 'image_url': 'https://example.test/n.jpg',
        }, format='json')
        self.assertEqual(response.data['status'], DesignAsset.Status.PENDING)

    def test_status_cannot_be_set_by_posting_it(self):
        self.config.design_approval_required = True
        self.config.save()
        tailor_client = self._staff_client('Tailor', 'sneaky@studio.test')
        response = tailor_client.post('/api/design-studio/assets/', {
            'title': 'Trying to skip the queue',
            'image_url': 'https://example.test/s.jpg',
            'status': DesignAsset.Status.ACTIVE,
        }, format='json')
        self.assertEqual(response.data['status'], DesignAsset.Status.PENDING)

    def test_approving_activates_the_design_and_records_who(self):
        asset = DesignAsset.objects.create(
            title="pending", image_url="https://example.test/p.jpg",
            status=DesignAsset.Status.PENDING)
        response = self.client.post(
            f'/api/design-studio/assets/{asset.id}/review/',
            {'decision': 'APPROVED', 'note': 'Lovely work'}, format='json')
        self.assertEqual(response.status_code, 200)
        asset.refresh_from_db()
        self.assertEqual(asset.status, DesignAsset.Status.ACTIVE)
        self.assertEqual(asset.approved_by, self.owner)
        self.assertIsNotNone(asset.approved_at)

    def test_rejecting_archives_rather_than_deletes(self):
        # A rejected design is a decision worth keeping a record of, not a
        # design that silently disappears.
        asset = DesignAsset.objects.create(
            title="rejected", image_url="https://example.test/r.jpg",
            status=DesignAsset.Status.PENDING)
        self.client.post(f'/api/design-studio/assets/{asset.id}/review/',
                          {'decision': 'REJECTED'}, format='json')
        asset.refresh_from_db()
        self.assertEqual(asset.status, DesignAsset.Status.ARCHIVED)
        self.assertTrue(DesignAsset.objects.filter(id=asset.id).exists())

    def test_changes_requested_leaves_it_in_the_queue(self):
        asset = DesignAsset.objects.create(
            title="needs work", image_url="https://example.test/w.jpg",
            status=DesignAsset.Status.PENDING)
        self.client.post(f'/api/design-studio/assets/{asset.id}/review/',
                          {'decision': 'CHANGES_REQUESTED', 'note': 'Wrong colour tag'},
                          format='json')
        asset.refresh_from_db()
        self.assertEqual(asset.status, DesignAsset.Status.PENDING)

    def test_every_decision_is_logged_even_across_resubmission(self):
        asset = DesignAsset.objects.create(
            title="history", image_url="https://example.test/h.jpg",
            status=DesignAsset.Status.PENDING)
        self.client.post(f'/api/design-studio/assets/{asset.id}/review/',
                          {'decision': 'CHANGES_REQUESTED', 'note': 'first pass'}, format='json')
        self.client.post(f'/api/design-studio/assets/{asset.id}/review/',
                          {'decision': 'APPROVED', 'note': 'now good'}, format='json')
        response = self.client.get(f'/api/design-studio/assets/{asset.id}/approval-history/')
        self.assertEqual([r['decision'] for r in response.data], ['APPROVED', 'CHANGES_REQUESTED'])

    def test_a_tailor_cannot_review_a_design(self):
        asset = DesignAsset.objects.create(
            title="protected", image_url="https://example.test/g.jpg",
            status=DesignAsset.Status.PENDING)
        tailor_client = self._staff_client('Tailor', 'reviewer@studio.test')
        response = tailor_client.post(f'/api/design-studio/assets/{asset.id}/review/',
                                       {'decision': 'APPROVED'}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_an_invalid_decision_is_rejected(self):
        asset = DesignAsset.objects.create(
            title="x", image_url="https://example.test/x.jpg",
            status=DesignAsset.Status.PENDING)
        response = self.client.post(f'/api/design-studio/assets/{asset.id}/review/',
                                     {'decision': 'MAYBE'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_pending_queue_is_a_status_filter(self):
        DesignAsset.objects.create(title="p1", image_url="https://example.test/1.jpg",
                                    status=DesignAsset.Status.PENDING)
        DesignAsset.objects.create(title="p2", image_url="https://example.test/2.jpg",
                                    status=DesignAsset.Status.PENDING)
        response = self.client.get('/api/design-studio/assets/?status=PENDING')
        self.assertEqual({d['title'] for d in response.data}, {"p1", "p2"})


class DesignDashboardTests(StudioTestCase):
    """The module's landing counters, and the enriched portfolio."""

    def setUp(self):
        super().setUp()
        from apps.catalog.services import sync_global_templates
        sync_global_templates()
        self.priya = Designer.objects.create(name="Priya")

    def _asset(self, title, **kw):
        return DesignAsset.objects.create(
            title=title, image_url=f"https://example.test/{title}.jpg", **kw)

    def test_dashboard_is_a_single_call(self):
        self._asset("a", designer_ref=self.priya, view_count=10)
        self._asset("b", status=DesignAsset.Status.PENDING)
        response = self.client.get('/api/design-studio/dashboard/')
        self.assertEqual(response.status_code, 200)
        for key in ('total_designs', 'active_designs', 'designers', 'collections',
                    'pending_approval', 'recent_uploads', 'most_viewed',
                    'most_ordered', 'trending'):
            self.assertIn(key, response.data)

    def test_pending_approval_count_matches_the_queue(self):
        self._asset("p1", status=DesignAsset.Status.PENDING)
        self._asset("p2", status=DesignAsset.Status.PENDING)
        self._asset("active_one")
        response = self.client.get('/api/design-studio/dashboard/')
        self.assertEqual(response.data['pending_approval'], 2)

    def test_most_viewed_is_ranked_and_excludes_archived(self):
        self._asset("quiet", view_count=1)
        self._asset("loud", view_count=99)
        self._asset("loud_but_gone", view_count=500, status=DesignAsset.Status.ARCHIVED)
        response = self.client.get('/api/design-studio/dashboard/')
        titles = [d['title'] for d in response.data['most_viewed']]
        self.assertEqual(titles[0], "loud")
        self.assertNotIn("loud_but_gone", titles)

    def test_trending_excludes_designs_not_touched_recently(self):
        from django.utils import timezone
        from datetime import timedelta
        stale = self._asset("old_favourite", view_count=200)
        DesignAsset.objects.filter(pk=stale.pk).update(
            updated_at=timezone.now() - timedelta(days=30))
        fresh = self._asset("this_weeks_pick", view_count=5)
        response = self.client.get('/api/design-studio/dashboard/')
        titles = [d['title'] for d in response.data['trending']]
        self.assertIn("this_weeks_pick", titles)
        self.assertNotIn("old_favourite", titles)

    def test_portfolio_reports_a_designers_own_performance(self):
        self._asset("hers1", designer_ref=self.priya, view_count=10, order_count=2)
        self._asset("hers2", designer_ref=self.priya, view_count=30, order_count=1)
        self._asset("not_hers", designer_ref=Designer.objects.create(name="Ravi"))
        Collection.objects.create(designer=self.priya, name="Bridal")

        response = self.client.get(f'/api/design-studio/designers/{self.priya.id}/portfolio/')
        stats = response.data['stats']
        self.assertEqual(stats['total_views'], 40)
        self.assertEqual(stats['total_orders'], 3)
        self.assertEqual(stats['active'], 2)
        self.assertEqual(stats['collections'], 1)
        self.assertEqual(stats['most_viewed']['title'], "hers2")

    def test_portfolio_stats_are_empty_not_broken_for_a_new_designer(self):
        ravi = Designer.objects.create(name="Ravi")
        response = self.client.get(f'/api/design-studio/designers/{ravi.id}/portfolio/')
        self.assertEqual(response.data['stats']['total_views'], 0)
        self.assertIsNone(response.data['stats']['most_viewed'])


class DesignerLoginTests(StudioTestCase):
    """Turning a credited designer into an account, and what that account can
    then do. This is step 7: everything before it worked with Designer.user
    staying null forever."""

    def _designer(self, name="Priya", **kw):
        return Designer.objects.create(name=name, **kw)

    def test_owner_grants_a_login_by_email(self):
        priya = self._designer()
        response = self.client.post(
            f'/api/design-studio/designers/{priya.id}/create-login/',
            {'email': 'priya@studio.test'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['has_login'])
        priya.refresh_from_db()
        self.assertIsNotNone(priya.user_id)
        self.assertEqual(priya.email, 'priya@studio.test')

    def test_the_new_account_can_actually_log_in(self):
        priya = self._designer()
        response = self.client.post(
            f'/api/design-studio/designers/{priya.id}/create-login/',
            {'email': 'priya@studio.test'}, format='json')
        priya.refresh_from_db()
        # Was check_password('DesignerSecure2026!') -- a single literal shared
        # by every designer on the platform, published in this repository and
        # in the shipped JS bundle. The password is now generated per account
        # and returned on this one response, so the assertion is that the value
        # the owner is shown is the value that actually works.
        self.assertTrue(priya.user.check_password(response.data['bootstrap_password']))

    def test_each_designer_gets_a_different_password(self):
        first = self._designer()
        second = Designer.objects.create(name='Ira Nathan')
        a = self.client.post(f'/api/design-studio/designers/{first.id}/create-login/',
                             {'email': 'first@studio.test'}, format='json')
        b = self.client.post(f'/api/design-studio/designers/{second.id}/create-login/',
                             {'email': 'second@studio.test'}, format='json')
        self.assertNotEqual(a.data['bootstrap_password'], b.data['bootstrap_password'])

    def test_a_second_call_is_refused_not_silently_reissued(self):
        priya = self._designer()
        self.client.post(f'/api/design-studio/designers/{priya.id}/create-login/',
                          {'email': 'priya@studio.test'}, format='json')
        response = self.client.post(
            f'/api/design-studio/designers/{priya.id}/create-login/',
            {'email': 'priya-new@studio.test'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_an_existing_account_with_that_email_is_linked_not_duplicated(self):
        existing = User.objects.create_user(username='priya@studio.test',
                                             email='priya@studio.test', password='whatever')
        priya = self._designer()
        response = self.client.post(
            f'/api/design-studio/designers/{priya.id}/create-login/',
            {'email': 'priya@studio.test'}, format='json')
        self.assertEqual(response.status_code, 200)
        priya.refresh_from_db()
        self.assertEqual(priya.user_id, existing.id)

    def test_login_requires_an_email(self):
        priya = self._designer()
        response = self.client.post(
            f'/api/design-studio/designers/{priya.id}/create-login/', {}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_a_tailor_cannot_grant_a_login(self):
        priya = self._designer()
        tailor = self._staff_client('Tailor', 'notowner@studio.test')
        response = tailor.post(f'/api/design-studio/designers/{priya.id}/create-login/',
                                {'email': 'priya@studio.test'}, format='json')
        self.assertEqual(response.status_code, 403)

    def _designer_client(self, designer):
        client = APIClient()
        client.credentials(HTTP_X_TENANT_ID=self.tenant.schema_name)
        client.force_authenticate(user=designer.user)
        return client

    def test_the_designer_role_resolves_correctly_end_to_end(self):
        priya = self._designer()
        self.client.post(f'/api/design-studio/designers/{priya.id}/create-login/',
                          {'email': 'priya@studio.test'}, format='json')
        priya.refresh_from_db()
        from core.roles import resolve_user_role, DESIGNER
        self.assertEqual(resolve_user_role(priya.user), DESIGNER)

    def test_a_designer_can_upload_and_edit_their_own_design(self):
        priya = self._designer()
        self.client.post(f'/api/design-studio/designers/{priya.id}/create-login/',
                          {'email': 'priya@studio.test'}, format='json')
        priya.refresh_from_db()
        client = self._designer_client(priya)

        created = client.post('/api/design-studio/assets/', {
            'title': 'Hers', 'image_url': 'https://example.test/h.jpg',
            'designer_ref': str(priya.id),
        }, format='json')
        self.assertEqual(created.status_code, 201, created.data)

        edited = client.patch(f'/api/design-studio/assets/{created.data["id"]}/',
                               {'title': 'Hers, retitled'}, format='json')
        self.assertEqual(edited.status_code, 200, edited.data)
        self.assertEqual(edited.data['title'], 'Hers, retitled')

    def test_a_designer_cannot_edit_someone_elses_upload(self):
        priya = self._designer("Priya")
        ravi = self._designer("Ravi")
        self.client.post(f'/api/design-studio/designers/{priya.id}/create-login/',
                          {'email': 'priya@studio.test'}, format='json')
        self.client.post(f'/api/design-studio/designers/{ravi.id}/create-login/',
                          {'email': 'ravi@studio.test'}, format='json')
        priya.refresh_from_db()
        ravi.refresh_from_db()

        ravis_design = DesignAsset.objects.create(
            title="Ravi's", image_url="https://example.test/r.jpg", designer_ref=ravi)

        priyas_client = self._designer_client(priya)
        response = priyas_client.patch(f'/api/design-studio/assets/{ravis_design.id}/',
                                        {'title': 'Hijacked'}, format='json')
        self.assertEqual(response.status_code, 403)
        ravis_design.refresh_from_db()
        self.assertEqual(ravis_design.title, "Ravi's")

    def test_a_designer_cannot_delete_someone_elses_upload(self):
        priya = self._designer("Priya")
        ravi = self._designer("Ravi")
        self.client.post(f'/api/design-studio/designers/{priya.id}/create-login/',
                          {'email': 'priya@studio.test'}, format='json')
        priya.refresh_from_db()

        ravis_design = DesignAsset.objects.create(
            title="Ravi's", image_url="https://example.test/r.jpg", designer_ref=ravi)

        priyas_client = self._designer_client(priya)
        response = priyas_client.delete(f'/api/design-studio/assets/{ravis_design.id}/')
        self.assertEqual(response.status_code, 403)
        self.assertTrue(DesignAsset.objects.filter(pk=ravis_design.pk).exists())

    def test_a_designer_cannot_grant_their_own_extra_logins(self):
        # DesignerViewSet write access stays Owner-only; only upload/edit/
        # delete-own on DesignAssetViewSet are opened to a Designer.
        priya = self._designer("Priya")
        self.client.post(f'/api/design-studio/designers/{priya.id}/create-login/',
                          {'email': 'priya@studio.test'}, format='json')
        priya.refresh_from_db()
        other = self._designer("Ravi")
        response = self._designer_client(priya).post(
            f'/api/design-studio/designers/{other.id}/create-login/',
            {'email': 'ravi@studio.test'}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_a_designer_can_still_read_the_whole_library(self):
        # Read access is unchanged: SAFE_METHODS stay open to any authenticated
        # role, same as before a Designer could exist.
        priya = self._designer()
        self.client.post(f'/api/design-studio/designers/{priya.id}/create-login/',
                          {'email': 'priya@studio.test'}, format='json')
        priya.refresh_from_db()
        response = self._designer_client(priya).get('/api/design-studio/assets/')
        self.assertEqual(response.status_code, 200)


class UploadAttributionTests(StudioTestCase):
    """What the browser actually posts, and who ends up credited."""

    def _designer_client(self, name="Priya", email="priya@studio.test"):
        user = User.objects.create_user(username=email, email=email, password="pass12345")
        Designer.objects.create(name=name, email=email, user=user)
        client = APIClient()
        client.credentials(HTTP_X_TENANT_ID=self.tenant.schema_name)
        client.force_authenticate(user=user)
        return client

    def test_multipart_json_fields_are_decoded_not_stored_as_text(self):
        """The browser always posts multipart and api.js JSON.stringify()s
        these fields. create() rebuilds request.data as a plain dict, which
        defeats DRF's HTML-input detection, so the JSON arrived as a string and
        was saved verbatim -- every library filter then matched nothing. The
        existing coverage posts format='json', which no browser does.
        """
        response = self.client.post(
            '/api/design-studio/assets/',
            {'title': 'Multipart Lehenga', 'garment_type': 'Lehenga',
             'image_url': 'https://example.test/l.jpg',
             'tags': '["Bridal", "Maroon"]',
             'attributes': '{"neckline_style": "Sweetheart"}'},
            format='multipart')

        self.assertEqual(response.status_code, 201)
        asset = DesignAsset.objects.get(title='Multipart Lehenga')
        self.assertEqual(asset.tags, ["Bridal", "Maroon"])
        self.assertEqual(asset.attributes, {"neckline_style": "Sweetheart"})

    def test_a_designer_is_credited_on_their_own_upload(self):
        """The Upload modal leaves designer_ref empty and api.js drops empty
        values, so a designer's own work was saved Unattributed -- and the
        permission carve-out that lets them edit their own uploads is keyed on
        designer_ref, so they were locked out of it immediately.
        """
        client = self._designer_client()

        response = client.post(
            '/api/design-studio/assets/',
            {'title': 'Her Own Work', 'garment_type': 'Lehenga',
             'image_url': 'https://example.test/h.jpg'},
            format='multipart')

        self.assertEqual(response.status_code, 201)
        asset = DesignAsset.objects.get(title='Her Own Work')
        self.assertIsNotNone(asset.designer_ref)
        self.assertEqual(asset.designer_ref.name, "Priya")

    def test_an_explicit_designer_still_wins(self):
        ravi = Designer.objects.create(name="Ravi")
        client = self._designer_client(name="Priya2", email="priya2@studio.test")

        client.post(
            '/api/design-studio/assets/',
            {'title': 'Credited To Ravi', 'garment_type': 'Lehenga',
             'image_url': 'https://example.test/r.jpg',
             'designer_ref': str(ravi.id)},
            format='multipart')

        self.assertEqual(
            DesignAsset.objects.get(title='Credited To Ravi').designer_ref, ravi)


class DesignerBoundaryTests(StudioTestCase):
    """What a designer may write, and what must stay out of their hands."""

    def _designer(self, name="Priya", email="priya@studio.test"):
        user = User.objects.create_user(username=email, email=email, password="pass12345")
        designer = Designer.objects.create(name=name, email=email, user=user)
        client = APIClient()
        client.credentials(HTTP_X_TENANT_ID=self.tenant.schema_name)
        client.force_authenticate(user=user)
        return client, designer, user

    def _upload(self, client, title):
        return client.post('/api/design-studio/assets/', {
            'title': title, 'garment_type': 'Lehenga',
            'image_url': 'https://example.test/u.jpg',
        }, format='multipart')

    def test_a_designer_cannot_patch_their_upload_into_the_catalogue(self):
        """`source` decides what the customer-facing gallery contains, and it
        was writable -- so an unreviewed upload could be PATCHed straight past
        the approval queue with its status still PENDING.
        """
        client, _, _ = self._designer()
        asset_id = self._upload(client, 'Sneaky').data['id']

        client.patch(f'/api/design-studio/assets/{asset_id}/',
                     {'source': DesignAsset.SOURCE_CATALOGUE}, format='json')

        self.assertEqual(DesignAsset.objects.get(pk=asset_id).source, DesignAsset.SOURCE_UPLOAD)

    def test_ownership_follows_the_uploader_not_the_credit(self):
        """designer_ref is the CREDIT -- migration 0003 mints it from free text
        on catalogue rows. Keying edit rights on it handed a designer delete
        rights over owner-curated designs that merely carried their name.
        """
        client, designer, _ = self._designer()
        curated = DesignAsset.objects.create(
            title="Owner's catalogue piece", garment_type='Lehenga',
            source=DesignAsset.SOURCE_CATALOGUE,
            image_url='https://example.test/c.jpg',
            designer_ref=designer)          # credited to them, not theirs

        response = client.delete(f'/api/design-studio/assets/{curated.id}/')

        self.assertEqual(response.status_code, 403)
        self.assertTrue(DesignAsset.objects.filter(pk=curated.id).exists())

    def test_a_designer_still_owns_what_they_uploaded(self):
        client, _, _ = self._designer()
        asset_id = self._upload(client, 'Mine').data['id']

        self.assertEqual(
            client.patch(f'/api/design-studio/assets/{asset_id}/',
                         {'title': 'Mine, retitled'}, format='json').status_code, 200)
        self.assertEqual(
            client.delete(f'/api/design-studio/assets/{asset_id}/').status_code, 204)

    def test_the_roster_does_not_hand_out_colleagues_login_addresses(self):
        client, _, _ = self._designer()
        Designer.objects.create(name="Ravi", email="ravi@studio.test")

        rows = client.get('/api/design-studio/designers/').data

        self.assertTrue(rows)
        self.assertNotIn('email', rows[0])
        self.assertNotIn('has_login', rows[0])
        self.assertIn('email', self.client.get('/api/design-studio/designers/').data[0])

    def test_a_designer_can_read_the_garment_templates_their_form_needs(self):
        """The upload form's Garment dropdown is built from these. The viewset
        declared no permission policy and inherited the rule written for
        customers and money, which refuses a designer outright -- so every
        design they uploaded had no template and no spec tags.
        """
        client, _, _ = self._designer()

        self.assertEqual(client.get('/api/catalog/templates/').status_code, 200)

    def test_granting_a_login_on_the_owners_address_is_refused(self):
        """resolve_user_role answers a Designer profile before it falls through
        to OWNER, so this made the boutique owner a Designer -- permanently,
        because every screen that could undo it is then refused to them.
        """
        designer = Designer.objects.create(name="Trap")

        response = self.client.post(
            f'/api/design-studio/designers/{designer.id}/create-login/',
            {'email': 'owner@studio.test'}, format='json')

        self.assertEqual(response.status_code, 400)
        designer.refresh_from_db()
        self.assertIsNone(designer.user_id)

    def test_removing_a_designer_does_not_leave_an_owner_behind(self):
        """Designer.user is SET_NULL, so the login was detached and left with no
        profile at all -- which resolve_user_role answers as OWNER.
        """
        _, designer, user = self._designer(name="Leaving", email="leaving@studio.test")

        self.client.delete(f'/api/design-studio/designers/{designer.id}/')

        user.refresh_from_db()
        self.assertFalse(user.is_active)
