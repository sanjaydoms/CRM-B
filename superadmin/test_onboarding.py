"""Onboarding progress and health, with the seed data present.

The central test is the first one. A boutique an hour old already holds four
tailors, eleven designs, eight stock locations, fifteen garment templates and
several hundred catalogue items, none of which it put there. If any of that
counts as progress, this whole feature reports a platform full of fully
onboarded boutiques that have never had a customer -- so the test seeds a real
tenant exactly the way signup does, asserts the seed data is genuinely there,
and then asserts the percentage is zero anyway.

Migrated tenants are kept to the minimum the assertions actually need. Creating
one runs every TENANT_APPS migration against a new Postgres schema and is by far
the slowest thing here, so a test only takes one when it has to read a real
schema; the unreadable-schema cases use a registry row whose schema was never
created, which is the same failure at no cost. Nothing about the module switches
needs a second schema either -- `enabled_modules` lives on the registry row, so
flipping it and calling progress() again reads the same boutique twice.
"""

from contextlib import contextmanager

from django.contrib.auth.models import User
from django.db import connection
from django.test import TransactionTestCase
from django_tenants.utils import schema_context

from apps.catalog.models import GarmentTemplate
from apps.design_studio.models import DesignAsset
from apps.inventory.models import CatalogItem, StockLocation, Supplier
from core.modules import MODULES
from crm_api.models import (BoutiqueSettings, Customer, CustomerMessage, Order,
                            Tailor)
from crm_api.serializers import BoutiqueDesignSerializer
from crm_api.utils import seed_tenant_defaults
from tenants.models import BoutiqueTenant

from . import health, onboarding
# The same helper the rest of the console's tests use. Schema creation is DDL,
# so these are TransactionTestCase and the tenant is built in the test body.
from .tests import temporary_tenant

STATUSES = {'healthy', 'warning', 'degraded', 'critical', 'offline',
            'not_configured'}


@contextmanager
def ghost_tenant(schema_name='sa_ghost', owner_email='ghost@onb.test'):
    """A registry row pointing at a schema that does not exist.

    Exactly what a half-created boutique looks like -- SignupView creates the
    tenant row and the schema in two steps, and a crash between them leaves
    this. auto_create_schema is turned off on the instance so no schema is
    built, and the row is removed through the queryset so TenantMixin.delete
    never goes looking for a schema to drop.
    """
    connection.set_schema_to_public()
    tenant = BoutiqueTenant(schema_name=schema_name, owner_email=owner_email,
                            name='Ghost Atelier')
    tenant.auto_create_schema = False
    tenant.save()
    try:
        yield tenant
    finally:
        connection.set_schema_to_public()
        BoutiqueTenant.objects.filter(pk=tenant.pk).delete()


def sign_up_like_the_real_thing(schema_name, owner_email):
    """Reproduce the state SignupView leaves a brand new boutique in.

    Deliberately the *worst* case for this feature: the owner gave no business
    address and no mobile number, so BoutiqueSettings keeps its class defaults
    for address and phone, which is the pair that would look "filled in" to
    anything checking for emptiness instead of for the default.
    """
    with schema_context(schema_name):
        seed_tenant_defaults()
        BoutiqueSettings.objects.update_or_create(
            id=1, defaults={'name': "Priya's Boutique", 'email': owner_email})
        User.objects.create_user(username=owner_email, email=owner_email,
                                 password='owner-pass-12345')


def do_everything_except_design_studio(schema_name, owner_email):
    """Complete every tracked step whose screens are not behind design_studio.

    Nine of the twelve: the three profile fields, a staff account, a specialist
    role, a customer, an order, a message actually sent, and stock. Deliberately
    leaves BoutiqueSettings.design_approval_required alone -- a boutique that
    never opens that switch is the normal case, and the point of the tests below
    is that it reaches 100% anyway.
    """
    with schema_context(schema_name):
        profile = BoutiqueSettings.objects.get(id=1)
        profile.logo = 'fabrics/priya-logo.png'
        profile.address = '14 Residency Road, Bengaluru'
        profile.phone = '+91 9812345678'
        profile.save()

        User.objects.create_user(username='cutter@onb.test', email='cutter@onb.test',
                                 password='staff-pass-12345')
        Tailor.objects.create(name='Devi K', specialty='Cutting',
                              role='Cutting Master')

        customer = Customer.objects.create(first_name='Nita', last_name='R',
                                           mobile_number='9000000031')
        order = Order.objects.create(order_id='ONB-DONE-1', customer=customer,
                                     total_amount=1000, order_status='Received')
        CustomerMessage.objects.create(
            order=order, template_key='order_confirmation',
            to_number='9000000031', body='Your order is confirmed.', status='SENT')

        Supplier.objects.create(name='Chandni Chowk Fabrics')


class OnboardingProgressTests(TransactionTestCase):

    def setUp(self):
        connection.set_schema_to_public()

    def test_seeded_data_does_not_count_and_real_work_does(self):
        with temporary_tenant('sa_onb', 'owner@onb.test', 'Onboarding Atelier') as tenant:
            sign_up_like_the_real_thing('sa_onb', 'owner@onb.test')

            with schema_context('sa_onb'):
                # If these ever stop being true the test below is measuring
                # nothing, so assert the trap is actually set before checking
                # that we did not fall into it.
                self.assertEqual(Tailor.objects.count(), 4)
                self.assertEqual(DesignAsset.objects.count(), 11)
                self.assertGreater(CatalogItem.objects.count(), 100)
                self.assertGreater(StockLocation.objects.count(), 0)
                self.assertGreater(GarmentTemplate.objects.count(), 0)

            fresh = onboarding.progress(tenant)
            self.assertTrue(fresh['readable'])

            # The whole point. Hundreds of seeded rows, zero real signals.
            self.assertEqual(fresh['percent'], 0)
            self.assertEqual(fresh['status'], 'not_started')
            self.assertEqual(fresh['completed_steps'], 0)

            done = {step['key']: step['done'] for step in fresh['steps']}
            self.assertFalse(done['staff_added'])        # 4 seeded tailors
            self.assertFalse(done['specialist_roles'])   # all Master/Tailor
            self.assertFalse(done['real_inventory'])     # ~730 catalogue items
            self.assertFalse(done['first_customer'])
            self.assertFalse(done['first_order'])
            self.assertFalse(done['address_set'])        # still the class default
            self.assertFalse(done['phone_set'])
            self.assertFalse(done['logo_uploaded'])

            # The blockage the console shows is the first unfinished step.
            self.assertEqual(fresh['blocked_on']['key'], 'logo_uploaded')

            # A customer and an order: the first two things a boutique does that
            # nothing on the platform could have done for it.
            with schema_context('sa_onb'):
                customer = Customer.objects.create(
                    first_name='Nita', last_name='R', mobile_number='9000000031')
                Order.objects.create(order_id='ONB-1', customer=customer,
                                     total_amount=1000, order_status='Received')

            after = onboarding.progress(tenant)
            moved = {step['key']: step['done'] for step in after['steps']}
            self.assertTrue(moved['first_customer'])
            self.assertTrue(moved['first_order'])
            self.assertEqual(after['completed_steps'], 2)
            self.assertEqual(after['status'], 'in_progress')
            self.assertEqual(after['percent'],
                             round(100 * 2 / after['tracked_steps']))
            # Everything else stayed put: the two new rows moved two steps.
            self.assertFalse(moved['staff_added'])
            self.assertFalse(moved['real_inventory'])

    def test_untracked_steps_are_not_reported_as_incomplete(self):
        """Against a real boutique, because a ghost has no steps to check.

        This used to run against a tenant whose schema was never created, whose
        progress() returns steps == [] -- so the loop over the untracked steps
        had nothing to iterate and `done is None` was never once asserted. The
        test passed by not executing.
        """
        with temporary_tenant('sa_untr', 'owner@untr.test', 'Untracked Atelier') as tenant:
            sign_up_like_the_real_thing('sa_untr', 'owner@untr.test')

            report = onboarding.progress(tenant)
            self.assertTrue(report['readable'])
            steps = {step['key']: step for step in report['steps']}

            expected = {'email_verified', 'phone_verified', 'whatsapp_connected',
                        'payment_configured', 'integrations_configured',
                        # Demoted from tracked: their signals were wrong rather
                        # than missing. See onboarding.UNTRACKED.
                        'real_designs', 'design_approval_configured'}
            self.assertEqual({key for key, _label, _detail in onboarding.UNTRACKED},
                             expected)

            for key in expected:
                step = steps[key]
                # done is None, never False: False is the red cross, and a cross
                # here accuses a boutique of skipping something unmeasurable.
                self.assertIsNone(step['done'], key)
                self.assertFalse(step['tracked'], key)
                self.assertEqual(step['state'], 'untracked', key)
                # An honest sentence, not an empty string the console renders as
                # a blank cell next to that cross.
                self.assertGreater(len(step['detail']), 40, key)

            # And they are genuinely out of the arithmetic, not merely rendered
            # differently: the denominator counts the steps that are scored.
            self.assertEqual(report['tracked_steps'],
                             len(report['steps']) - len(expected))
            self.assertNotIn(report['blocked_on']['key'], expected)

    def test_a_switched_off_module_is_excluded_rather_than_held_against(self):
        """The defect this rewrite exists for, in its sharpest form.

        One boutique, one switch, nothing else changed. With Design Studio on,
        three steps it cannot reach hold it at 75% for ever, and the console
        names 'designers' as what it is stuck on -- a screen its own
        administrator made TenantHeaderMiddleware refuse. With Design Studio
        off, the same boutique is finished, which it is.

        `design_approval_required` is left at its shipped False throughout, so
        reaching 100% here is also the proof that a two-state boolean nobody has
        ever touched no longer holds a completed boutique below the line.
        """
        with temporary_tenant('sa_mod', 'owner@mod.test', 'Module Atelier') as tenant:
            sign_up_like_the_real_thing('sa_mod', 'owner@mod.test')
            do_everything_except_design_studio('sa_mod', 'owner@mod.test')

            on = onboarding.progress(tenant)
            self.assertEqual(on['completed_steps'], 9)
            self.assertEqual(on['tracked_steps'], 12)
            self.assertEqual(on['percent'], 75)
            self.assertEqual(on['blocked_on']['key'], 'designers')

            with schema_context('sa_mod'):
                self.assertFalse(
                    BoutiqueSettings.objects.get(id=1).design_approval_required)

            tenant.enabled_modules = {'design_studio': False}

            off = onboarding.progress(tenant)
            self.assertEqual(off['completed_steps'], 9)
            self.assertEqual(off['tracked_steps'], 9)
            self.assertEqual(off['percent'], 100)
            self.assertEqual(off['status'], 'completed')
            self.assertIsNone(off['blocked_on'])

            gated = {step['key']: step for step in off['steps']
                     if step['state'] == 'module_off'}
            self.assertEqual(set(gated), {'designers', 'collections', 'boards'})
            for key, step in gated.items():
                # Neither done nor failed. False would put the red cross back.
                self.assertIsNone(step['done'], key)
                self.assertFalse(step['tracked'], key)
                self.assertEqual(step['module'], 'design_studio', key)
                # Names the module and the URLs, so the administrator reading
                # the row can see it is their own switch and not the boutique.
                self.assertIn('Design Studio', step['detail'], key)
                self.assertIn('/api/design-studio/', step['detail'], key)
            self.assertIn('module switched off', off['percent_basis'])

            # Switching it back on restores the three steps and the blockage:
            # nothing here is sticky.
            tenant.enabled_modules = {'design_studio': True}
            self.assertEqual(onboarding.progress(tenant)['percent'], 75)

    def test_every_step_names_a_module_that_can_actually_be_switched_off(self):
        """The step-to-module table, checked against core.modules rather than read.

        A key with a typo in it would never match anything in enabled_modules,
        so the step would stay scored and the defect would be back with no test
        failing. A key on a step whose screens are elsewhere is worse: the
        boutique loses a step it can still complete.
        """
        with temporary_tenant('sa_map', 'owner@map.test', 'Mapping Atelier') as tenant:
            sign_up_like_the_real_thing('sa_map', 'owner@map.test')
            modules = {step['key']: step['module']
                       for step in onboarding.progress(tenant)['steps']}

            self.assertEqual(
                {key: value for key, value in modules.items() if value},
                {'staff_added': 'tailors',
                 'specialist_roles': 'tailors',
                 'designers': 'design_studio',
                 'collections': 'design_studio',
                 'boards': 'design_studio',
                 # 'inventory', not 'inventory_catalog': the narrower module
                 # owns CatalogItem, which this step refuses to count anyway.
                 'real_inventory': 'inventory'})
            for key, value in modules.items():
                if value is not None:
                    self.assertIn(value, MODULES, key)

            # The rest name nothing, and must: the profile is on an ALWAYS_ON
            # prefix, and customers, orders and messaging are STRUCTURAL in
            # core.modules -- there is no switch that could turn them off, so
            # excluding them for one would be excusing work nobody prevented.
            self.assertEqual(
                {key for key, value in modules.items() if value is None},
                {'logo_uploaded', 'address_set', 'phone_set', 'first_customer',
                 'first_order', 'communication', 'email_verified',
                 'phone_verified', 'whatsapp_connected', 'payment_configured',
                 'integrations_configured', 'real_designs',
                 'design_approval_configured'})

            # Both keys really gate, not just design_studio.
            tenant.enabled_modules = {'tailors': False, 'inventory': False}
            states = {step['key']: step['state']
                      for step in onboarding.progress(tenant)['steps']}
            for key in ('staff_added', 'specialist_roles', 'real_inventory'):
                self.assertEqual(states[key], 'module_off', key)
            self.assertEqual(states['designers'], 'todo')

    def test_a_design_the_boutique_added_is_indistinguishable_from_seed_data(self):
        """Why 'Own designs in the library' is untracked rather than counted.

        The step used to be scored as "source is not catalogue/suggestion", and
        BoutiqueDesignSerializer stamps source=catalogue on every design saved
        from the boutique's own Manage Designs screen -- so a boutique adding
        designs scored zero for it and the step could never complete.

        The obvious replacement, created_by, does not separate them either:
        neither the serializer nor BoutiqueDesignViewSet sets it, and neither
        does the seeder. This test pins that. If someone later makes the write
        path record its author, the last two assertions fail and this step can
        go back to being scored.
        """
        with temporary_tenant('sa_dsn', 'owner@dsn.test', 'Designs Atelier') as tenant:
            sign_up_like_the_real_thing('sa_dsn', 'owner@dsn.test')

            with schema_context('sa_dsn'):
                # Exactly what POST /api/boutique-designs/ does.
                serializer = BoutiqueDesignSerializer(data={
                    'name': 'Ruby Bridal Lehenga',
                    'garment_type': 'Lehenga',
                    'image_url': 'https://example.test/ruby.jpg',
                    'description': "The boutique's own design.",
                    'price': '42000.00',
                    'is_boutique': True,
                })
                serializer.is_valid(raise_exception=True)
                design = serializer.save()

                self.assertEqual(design.source, DesignAsset.SOURCE_CATALOGUE)
                self.assertIsNone(design.created_by)
                self.assertEqual(design.external_id, '')

                # The two candidate signals, against a schema where the boutique
                # has demonstrably added a design of its own.
                self.assertEqual(
                    DesignAsset.objects.exclude(
                        source__in=(DesignAsset.SOURCE_CATALOGUE,
                                    DesignAsset.SOURCE_SUGGESTION)).count(), 0)
                self.assertEqual(
                    DesignAsset.objects.filter(created_by__isnull=False).count(), 0)
                self.assertEqual(DesignAsset.objects.count(), 12)

            report = onboarding.progress(tenant)
            step = next(s for s in report['steps'] if s['key'] == 'real_designs')
            self.assertIsNone(step['done'])
            self.assertEqual(step['state'], 'untracked')
            self.assertNotIn('real_designs',
                             [s['key'] for s in report['steps'] if s['tracked']])

    def test_a_missing_schema_reports_unreadable_rather_than_zero(self):
        """The distinction the whole feature turns on.

        0% means "this boutique has done nothing" and someone should call them.
        Unreadable means "the schema is broken" and someone should fix it. A
        broken schema that reported 0% would send the wrong person.
        """
        with ghost_tenant() as ghost:
            report = onboarding.progress(ghost)

            self.assertFalse(report['readable'])
            self.assertEqual(report['status'], 'unreadable')
            self.assertIsNone(report['percent'])
            self.assertIsNone(report['blocked_on'])
            self.assertEqual(report['steps'], [])
            self.assertIn('could not be read', report['detail'])

            # steps() must not raise either -- it is the same code path.
            self.assertEqual(onboarding.steps(ghost), [])

    def test_the_public_schema_is_not_a_boutique(self):
        registry = BoutiqueTenant(schema_name='public',
                                  owner_email='registry@onb.test', name='Public')
        registry.auto_create_schema = False
        self.assertEqual(onboarding.progress(registry)['status'], 'unreadable')


class HealthCheckTests(TransactionTestCase):
    """A health page is opened when something is already broken, so the only
    unforgivable behaviour is raising."""

    def setUp(self):
        connection.set_schema_to_public()

    def test_every_check_reports_and_none_of_them_raises(self):
        with ghost_tenant():
            results = health.checks()

            self.assertEqual(
                [check['key'] for check in results],
                ['database', 'migrations', 'tenant_schemas', 'media_storage',
                 'email', 'supabase_storage', 'errors', 'whatsapp', 'payments',
                 'background_jobs', 'sms'])

            by_key = {check['key']: check for check in results}
            for check in results:
                self.assertIn(check['status'], STATUSES)
                self.assertTrue(check['detail'], check['key'])
                self.assertTrue(check['label'], check['key'])

            # The one boutique in the registry has no schema, so this must not
            # come back green -- that is the whole reason the check exists.
            self.assertIn(by_key['tenant_schemas']['status'],
                          ('degraded', 'critical'))

            self.assertIn(by_key['database']['status'], ('healthy', 'warning'))

            # Deliberate product decisions, not faults. A red light on any of
            # these sends somebody hunting a bug that does not exist.
            for key in ('whatsapp', 'payments', 'background_jobs', 'sms'):
                self.assertEqual(by_key[key]['status'], 'not_configured', key)
            self.assertIn('by hand', by_key['whatsapp']['detail'])
            # Supabase is never green: the storage driver is bypassed entirely.
            self.assertEqual(by_key['supabase_storage']['status'], 'not_configured')

    def test_checks_run_with_no_tenants_at_all(self):
        self.assertEqual(
            {check['key'] for check in health.checks()},
            {'database', 'migrations', 'tenant_schemas', 'media_storage',
             'email', 'supabase_storage', 'errors', 'whatsapp', 'payments',
             'background_jobs', 'sms'})
