"""AI Design Studio.

Covers the three things the feature promises and could quietly get wrong: that
recommendations are explained and stable, that the design a tailor sees is the
one the owner approved, and that the role split in the spec is actually
enforced rather than assumed by the UI.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.db.utils import IntegrityError
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from rest_framework.test import APIClient

from crm_api.models import BoutiqueDesign, Customer, FabricSelection, Measurement, Order, Tailor

from .context import build_context
from .intelligence.rules import RuleBasedIntelligence
from .models import Designer, DesignAsset, DesignBoard, DesignBoardItem
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

        self.design = BoutiqueDesign.objects.create(
            name="Maroon Bridal Lehenga", garment_type="Lehenga",
            neckline_style="Sweetheart", sleeve_style="Half Sleeve",
            image_url="https://example.test/lehenga.jpg", price=Decimal('35000'),
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
        DesignAsset.objects.create(title="anon", image_url="https://example.test/anon.jpg")
        self._run_backfill()
        self.assertEqual(Designer.objects.count(), 0)
        self.assertIsNone(DesignAsset.objects.get().designer_ref_id)

    def test_running_it_twice_creates_nothing_extra(self):
        DesignAsset.objects.create(
            title="a", image_url="https://example.test/a.jpg", designer="Priya")
        self._run_backfill()
        self._run_backfill()
        self.assertEqual(Designer.objects.count(), 1)
