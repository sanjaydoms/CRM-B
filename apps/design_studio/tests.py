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
