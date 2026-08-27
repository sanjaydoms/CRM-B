
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
from .tests import temporary_tenant

STATUSES = {'healthy', 'warning', 'degraded', 'critical', 'offline',
            'not_configured'}


@contextmanager
def ghost_tenant(schema_name='sa_ghost', owner_email='ghost@onb.test'):
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
    with schema_context(schema_name):
        seed_tenant_defaults()
        BoutiqueSettings.objects.update_or_create(
            id=1, defaults={'name': "Priya's Boutique", 'email': owner_email})
        User.objects.create_user(username=owner_email, email=owner_email,
                                 password='owner-pass-12345')


def do_everything_except_design_studio(schema_name, owner_email):
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
                self.assertEqual(Tailor.objects.count(), 4)
                self.assertEqual(DesignAsset.objects.count(), 11)
                self.assertGreater(CatalogItem.objects.count(), 100)
                self.assertGreater(StockLocation.objects.count(), 0)
                self.assertGreater(GarmentTemplate.objects.count(), 0)

            fresh = onboarding.progress(tenant)
            self.assertTrue(fresh['readable'])

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

            self.assertEqual(fresh['blocked_on']['key'], 'logo_uploaded')

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
            self.assertFalse(moved['staff_added'])
            self.assertFalse(moved['real_inventory'])

    def test_untracked_steps_are_not_reported_as_incomplete(self):
        with temporary_tenant('sa_untr', 'owner@untr.test', 'Untracked Atelier') as tenant:
            sign_up_like_the_real_thing('sa_untr', 'owner@untr.test')

            report = onboarding.progress(tenant)
            self.assertTrue(report['readable'])
            steps = {step['key']: step for step in report['steps']}

            expected = {'email_verified', 'phone_verified', 'whatsapp_connected',
                        'payment_configured', 'integrations_configured',
                        'real_designs', 'design_approval_configured'}
            self.assertEqual({key for key, _label, _detail in onboarding.UNTRACKED},
                             expected)

            for key in expected:
                step = steps[key]
                self.assertIsNone(step['done'], key)
                self.assertFalse(step['tracked'], key)
                self.assertEqual(step['state'], 'untracked', key)
                self.assertGreater(len(step['detail']), 40, key)

            self.assertEqual(report['tracked_steps'],
                             len(report['steps']) - len(expected))
            self.assertNotIn(report['blocked_on']['key'], expected)

    def test_a_switched_off_module_is_excluded_rather_than_held_against(self):
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
                self.assertIsNone(step['done'], key)
                self.assertFalse(step['tracked'], key)
                self.assertEqual(step['module'], 'design_studio', key)
                self.assertIn('Design Studio', step['detail'], key)
                self.assertIn('/api/design-studio/', step['detail'], key)
            self.assertIn('module switched off', off['percent_basis'])

            tenant.enabled_modules = {'design_studio': True}
            self.assertEqual(onboarding.progress(tenant)['percent'], 75)

    def test_every_step_names_a_module_that_can_actually_be_switched_off(self):
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
                 'real_inventory': 'inventory'})
            for key, value in modules.items():
                if value is not None:
                    self.assertIn(value, MODULES, key)

            self.assertEqual(
                {key for key, value in modules.items() if value is None},
                {'logo_uploaded', 'address_set', 'phone_set', 'first_customer',
                 'first_order', 'communication', 'email_verified',
                 'phone_verified', 'whatsapp_connected', 'payment_configured',
                 'integrations_configured', 'real_designs',
                 'design_approval_configured'})

            tenant.enabled_modules = {'tailors': False, 'inventory': False}
            states = {step['key']: step['state']
                      for step in onboarding.progress(tenant)['steps']}
            for key in ('staff_added', 'specialist_roles', 'real_inventory'):
                self.assertEqual(states[key], 'module_off', key)
            self.assertEqual(states['designers'], 'todo')

    def test_a_design_the_boutique_added_is_indistinguishable_from_seed_data(self):
        with temporary_tenant('sa_dsn', 'owner@dsn.test', 'Designs Atelier') as tenant:
            sign_up_like_the_real_thing('sa_dsn', 'owner@dsn.test')

            with schema_context('sa_dsn'):
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
        with ghost_tenant() as ghost:
            report = onboarding.progress(ghost)

            self.assertFalse(report['readable'])
            self.assertEqual(report['status'], 'unreadable')
            self.assertIsNone(report['percent'])
            self.assertIsNone(report['blocked_on'])
            self.assertEqual(report['steps'], [])
            self.assertIn('could not be read', report['detail'])

            self.assertEqual(onboarding.steps(ghost), [])

    def test_the_public_schema_is_not_a_boutique(self):
        registry = BoutiqueTenant(schema_name='public',
                                  owner_email='registry@onb.test', name='Public')
        registry.auto_create_schema = False
        self.assertEqual(onboarding.progress(registry)['status'], 'unreadable')


class HealthCheckTests(TransactionTestCase):

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

            self.assertIn(by_key['tenant_schemas']['status'],
                          ('degraded', 'critical'))

            self.assertIn(by_key['database']['status'], ('healthy', 'warning'))

            for key in ('whatsapp', 'payments', 'background_jobs', 'sms'):
                self.assertEqual(by_key[key]['status'], 'not_configured', key)
            self.assertIn('by hand', by_key['whatsapp']['detail'])
            self.assertEqual(by_key['supabase_storage']['status'], 'not_configured')

    def test_checks_run_with_no_tenants_at_all(self):
        self.assertEqual(
            {check['key'] for check in health.checks()},
            {'database', 'migrations', 'tenant_schemas', 'media_storage',
             'email', 'supabase_storage', 'errors', 'whatsapp', 'payments',
             'background_jobs', 'sms'})
