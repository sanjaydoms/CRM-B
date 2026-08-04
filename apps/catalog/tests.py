"""Tests for the template engine.

The rules here are the ones a wrong answer costs fabric over: a hidden field that
is still demanded, an option that no longer exists, a measurement typed with an
extra zero.
"""

from django_tenants.test.cases import TenantTestCase

from core.templates import SpecValidationError, is_visible, validate_spec

from .models import GarmentJob, GarmentTemplate
from .services import sync_global_templates


class CatalogTestCase(TenantTestCase):
    """Templates live in the tenant schema, so every test needs one."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = 'catalog@test.com'
        tenant.name = "Catalog Test Boutique"
        return tenant

    def setUp(self):
        super().setUp()
        sync_global_templates()


class TemplateSeedTests(CatalogTestCase):
    def test_all_twelve_garments_are_seeded(self):
        self.assertEqual(GarmentTemplate.objects.filter(tenant__isnull=True).count(), 12)

    def test_every_template_has_all_five_sections(self):
        for template in GarmentTemplate.objects.all():
            keys = [s.key for s in template.sections.all()]
            self.assertEqual(
                keys, ['basic', 'measurements', 'style', 'materials', 'production'],
                f"{template.key} is missing a section",
            )

    def test_common_fields_reach_every_garment(self):
        for template in GarmentTemplate.objects.all():
            keys = {f.key for s in template.sections.all() for f in s.fields.all()}
            self.assertIn('delivery_date', keys)
            self.assertIn('special_instructions', keys)
            self.assertIn('urgency', keys)

    def test_field_keys_are_unique_within_a_template(self):
        for template in GarmentTemplate.objects.all():
            keys = [f.key for s in template.sections.all() for f in s.fields.all()]
            self.assertEqual(len(keys), len(set(keys)), f"{template.key} has a duplicate key")

    def test_measurement_keys_mean_the_same_thing_across_garments(self):
        # Shared keys are what make measurement history and the cutting sheet
        # comparable; a blouse and a lehenga blouse must not diverge.
        def measurements(key):
            template = GarmentTemplate.resolve(key)
            section = template.sections.get(key='measurements')
            return {f.key for f in section.fields.all()}

        self.assertEqual(measurements('blouse'), measurements('lehenga_blouse'))

    def test_syncing_twice_does_not_duplicate(self):
        sync_global_templates()
        self.assertEqual(GarmentTemplate.objects.filter(tenant__isnull=True).count(), 12)

    def test_resync_bumps_the_version(self):
        before = GarmentTemplate.resolve('saree').version
        sync_global_templates()
        self.assertEqual(GarmentTemplate.resolve('saree').version, before + 1)


class VisibilityTests(CatalogTestCase):
    def _field(self, template_key, field_key):
        template = GarmentTemplate.resolve(template_key)
        for section in template.sections.all():
            for field in section.fields.all():
                if field.key == field_key:
                    return field
        raise AssertionError(f"{template_key}.{field_key} not found")

    def test_multiselect_membership_reveals_the_field(self):
        fall = self._field('saree', 'fall_type')
        self.assertTrue(is_visible(fall, {'services': ['fall_pico']}))
        self.assertTrue(is_visible(fall, {'services': ['stitching', 'fall']}))
        self.assertFalse(is_visible(fall, {'services': ['stitching']}))

    def test_boolean_rule(self):
        colour = self._field('blouse', 'dori_colour')
        self.assertTrue(is_visible(colour, {'dori_required': True}))
        self.assertFalse(is_visible(colour, {'dori_required': False}))
        self.assertFalse(is_visible(colour, {}))

    def test_neq_rule_defaults_to_visible_when_unanswered(self):
        # Hand rounding applies to every sleeve except sleeveless, including
        # before a sleeve has been chosen.
        rounding = self._field('blouse', 'hand_rounding')
        self.assertTrue(is_visible(rounding, {}))
        self.assertFalse(is_visible(rounding, {'sleeve_length': 'sleeveless'}))


class ValidationTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        self.saree = GarmentTemplate.resolve('saree')
        self.valid = {
            'saree_type': 'silk',
            'services': ['fall_pico'],
            'delivery_date': '2026-09-01',
        }

    def test_a_good_spec_passes(self):
        cleaned = validate_spec(self.saree, self.valid)
        self.assertEqual(cleaned['saree_type'], 'silk')

    def test_required_fields_are_reported_together(self):
        with self.assertRaises(SpecValidationError) as caught:
            validate_spec(self.saree, {})
        # Delivery date is deliberately not here: an order is often taken before
        # a date is agreed, and requiring it only produced placeholder dates.
        self.assertEqual(set(caught.exception.errors), {'saree_type', 'services'})

    def test_delivery_date_is_optional_on_every_garment(self):
        for template in GarmentTemplate.objects.all():
            field = next(
                f for s in template.sections.all() for f in s.fields.all()
                if f.key == 'delivery_date'
            )
            self.assertFalse(field.is_required, f"{template.key} still demands a delivery date")

    def test_service_groups_appear_only_for_the_services_chosen(self):
        style = self.saree.sections.get(key='style')
        visible = lambda services: {
            f.key for f in style.fields.all() if is_visible(f, {'services': services})
        }

        # Fall and pico work asks nothing about borders, tassels or petticoats.
        self.assertEqual(visible(['fall_pico']), {'services', 'fall_type', 'pico_type'})
        # Stitching does not ask how the fall should be cut.
        self.assertEqual(
            visible(['stitching']), {'services', 'border', 'backing', 'petticoat_required'}
        )
        self.assertIn('tassels', visible(['tassel_work']))
        self.assertNotIn('tassels', visible(['stitching']))

    def test_tassel_material_needs_the_service_not_just_an_unset_field(self):
        # `neq` is true for an unanswered field, so without the service gate the
        # tassel material appeared on orders with no tassel work at all.
        materials = self.saree.sections.get(key='materials')
        tassels = next(f for f in materials.fields.all() if f.key == 'tassels_material')
        self.assertFalse(is_visible(tassels, {'services': ['stitching']}))
        self.assertTrue(
            is_visible(tassels, {'services': ['tassel_work'], 'tassels': 'hand_made'})
        )

    def test_hidden_fields_are_dropped_not_rejected(self):
        spec = {**self.valid, 'services': ['stitching'], 'fall_type': 'big_fall'}
        cleaned = validate_spec(self.saree, spec)
        self.assertNotIn('fall_type', cleaned)

    def test_a_required_field_that_is_hidden_is_not_demanded(self):
        blouse = GarmentTemplate.resolve('blouse')
        cleaned = validate_spec(
            blouse,
            {'blouse_type': 'plain', 'sleeve_length': 'sleeveless',
             'delivery_date': '2026-09-01'},
        )
        self.assertNotIn('hand_rounding', cleaned)

    def test_unknown_option_is_refused(self):
        with self.assertRaises(SpecValidationError) as caught:
            validate_spec(self.saree, {**self.valid, 'saree_type': 'denim'})
        self.assertIn('saree_type', caught.exception.errors)

    def test_unknown_key_is_refused_rather_than_silently_dropped(self):
        with self.assertRaises(SpecValidationError) as caught:
            validate_spec(self.saree, {**self.valid, 'waist_size': 30})
        self.assertIn('waist_size', caught.exception.errors)

    def test_measurement_out_of_range(self):
        churidar = GarmentTemplate.resolve('churidar')
        with self.assertRaises(SpecValidationError) as caught:
            validate_spec(churidar, {
                'full_length': '400', 'waist': '30', 'delivery_date': '2026-09-01',
            })
        self.assertIn('full_length', caught.exception.errors)

    def test_partial_relaxes_required_but_not_correctness(self):
        cleaned = validate_spec(self.saree, {'saree_type': 'silk'}, partial=True)
        self.assertEqual(cleaned, {'saree_type': 'silk'})
        with self.assertRaises(SpecValidationError):
            validate_spec(self.saree, {'saree_type': 'denim'}, partial=True)

    def test_trial_date_must_precede_delivery(self):
        with self.assertRaises(SpecValidationError) as caught:
            validate_spec(self.saree, {
                **self.valid, 'trial_required': True,
                'trial_date': '2026-09-20', 'delivery_date': '2026-09-01',
            })
        self.assertIn('trial_date', caught.exception.errors)

    def test_style_specific_fields_switch_with_the_style(self):
        lb = GarmentTemplate.resolve('lehenga_blouse')
        peplum = validate_spec(lb, {
            'blouse_style': 'peplum', 'flare_length': '12', 'flare_type': 'pleats',
            'delivery_date': '2026-09-01',
        })
        self.assertIn('flare_length', peplum)

        # The same answers under Corset must not carry the peplum flare across.
        corset = validate_spec(lb, {
            'blouse_style': 'corset', 'flare_length': '12', 'boning_required': True,
            'delivery_date': '2026-09-01',
        })
        self.assertNotIn('flare_length', corset)
        self.assertIn('boning_required', corset)


class GarmentJobTests(CatalogTestCase):
    def _order(self):
        from crm_api.models import Customer, Order
        customer = Customer.objects.create(
            first_name='Asha', last_name='R', mobile_number='9000000001',
        )
        return Order.objects.create(order_id='T2B-TEST-0001', customer=customer)

    def test_template_version_is_frozen_at_creation(self):
        template = GarmentTemplate.resolve('dupatta')
        job = GarmentJob.objects.create(
            order=self._order(), template=template,
            measurements={'length': '90', 'width': '36'},
        )
        self.assertEqual(job.template_version, template.version)

        sync_global_templates()  # the owner edits the template afterwards
        job.refresh_from_db()
        template.refresh_from_db()
        self.assertEqual(job.template_version, template.version - 1)

    def test_an_order_holds_several_dresses(self):
        order = self._order()
        for key in ('lehenga', 'lehenga_blouse', 'dupatta'):
            GarmentJob.objects.create(order=order, template=GarmentTemplate.resolve(key))
        self.assertEqual(order.garment_jobs.count(), 3)
