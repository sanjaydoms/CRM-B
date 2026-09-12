"""Guards on the module registry itself. No database, no tenant.

This module doubles as a fake URLconf: `urlpatterns` at the bottom mounts the
prefixes nothing governs, in every shape an app can be mounted in, so the
deploy-time check can be shown FAILING as well as passing. A check that has
only ever been seen to pass is not evidence.
"""

import sys
from unittest import mock

from django.http import HttpResponse
from django.test import SimpleTestCase, override_settings
from django.urls import include, path, re_path

from core import checks
from core.checks import (
    check_every_prefix_is_governed, check_production_roles_match_the_model,
    check_registry_is_consistent, mounted_prefixes,
)
from core.modules import (
    ALL_ROLES, MODULES, MODULE_GROUP, PRODUCTION_ROLES, ROLE_DEFAULTS,
    STRUCTURAL, catalogue, effective_modules, is_enabled, module_for_path,
    role_allows,
)

TAILOR_DEFAULT = ROLE_DEFAULTS['Tailor']


class RegistryChecksTests(SimpleTestCase):

    def test_every_mounted_prefix_is_accounted_for(self):
        # The failure this prevents: /api/email/ and /api/order-drafts/ shipped
        # ungoverned and answered for boutiques whose modules were switched off.
        self.assertEqual(check_every_prefix_is_governed(None), [])

    def test_the_walk_finds_the_prefixes_that_were_missed(self):
        found = set(mounted_prefixes())
        self.assertIn('/api/email/', found)
        self.assertIn('/api/order-drafts/', found)

    def test_registry_is_internally_consistent(self):
        self.assertEqual(check_registry_is_consistent(None), [])
        self.assertEqual(check_production_roles_match_the_model(None), [])

    @override_settings(ROOT_URLCONF='core.test_modules')
    def test_an_ungoverned_prefix_is_an_error(self):
        errors = check_every_prefix_is_governed(None)
        messages = [e.msg for e in errors]
        self.assertTrue(any('/api/marketing/' in m for m in messages), messages)
        self.assertEqual({e.id for e in errors}, {'core.E001'})
        # ...and a governed neighbour in the same fake urlconf stays quiet.
        self.assertFalse(any('/api/tailors/' in m for m in messages), messages)

    @override_settings(ROOT_URLCONF='core.test_modules')
    def test_an_app_that_adds_no_segment_of_its_own_is_reported(self):
        """The hole that made this whole check false comfort.

        include([path('', view)]) mounts an entire app on its prefix and adds
        no literal segment below it. The walk descended into it, found nothing
        to report, and said nothing -- so a Marketing app shaped like this
        would have landed ungoverned with core.E001 passing clean, which is
        worse than having no check at all.
        """
        messages = [e.msg for e in check_every_prefix_is_governed(None)]
        self.assertTrue(any(m.startswith('/api/marketing-b/ ') for m in messages), messages)

    @override_settings(ROOT_URLCONF='core.test_modules')
    def test_the_bus_prefix_is_descended_never_judged(self):
        # /api/ is governed by nothing and has to stay that way: judging it
        # would report the mount point every crm_api route lives under, and
        # stopping the walk there would hide the next order-drafts. So the
        # mount point is only judged when descending it found NOTHING -- a
        # root view alone is not enough, or the router's api-root would make
        # /api/ an error on the real urlconf.
        found = set(mounted_prefixes())
        self.assertNotIn('/api/', found)
        self.assertIn('/api/marketing/campaigns/', found)

    @override_settings(ROOT_URLCONF='core.test_modules')
    def test_the_router_api_root_and_its_format_twins_are_not_prefixes(self):
        # '' and '\.(?P<format>[a-z0-9]+)' are the mount point spelled two
        # ways, not two new prefixes. Reporting them would put a regex in an
        # error message and a second, unregisterable name on one endpoint.
        found = set(mounted_prefixes())
        self.assertFalse([p for p in found if 'format' in p or '(' in p], found)

    @override_settings(ROOT_URLCONF='core.test_modules')
    def test_a_mixed_app_is_reported_by_its_children(self):
        # A root view AND child routes. The children are reported, the mount
        # point is not -- the same answer /api/ gets, and for the same reason:
        # a root view under a resolver that also carries children rides on
        # whatever governs those children. Governance is startswith-shaped, so
        # registering /api/marketing-c/ (what a MODULES entry always is: a
        # mount point) silences the child AND covers the root view.
        found = set(mounted_prefixes())
        self.assertIn('/api/marketing-c/reports/', found)
        self.assertNotIn('/api/marketing-c/', found)

    @override_settings(ROOT_URLCONF='core.test_modules')
    def test_an_always_on_prefix_is_judged_whole_and_not_descended(self):
        # /admin/ answers for every boutique, and descending it would put three
        # hundred admin routes in the answer.
        found = set(mounted_prefixes())
        self.assertIn('/admin/', found)
        self.assertEqual([p for p in found if p.startswith('/admin/') and p != '/admin/'], [])
        self.assertFalse([e for e in check_every_prefix_is_governed(None)
                          if e.msg.startswith('/admin/')])

    def test_structural_prefixes_are_really_mounted(self):
        # checks.py writes these out instead of inferring f'/api/{key}/', a
        # key-equals-URL convention MODULES does not use. Written down means
        # they can be wrong; this is what says they are not.
        found = set(mounted_prefixes())
        for prefix in checks._STRUCTURAL_PREFIXES:
            with self.subTest(prefix=prefix):
                self.assertIn(prefix, found)
        self.assertEqual(len(checks._STRUCTURAL_PREFIXES), len(STRUCTURAL))

    def test_a_guard_that_cannot_run_is_reported_not_silenced(self):
        # It used to return [] on any exception, so a moved or renamed model
        # turned the only thing keeping PRODUCTION_ROLES honest into a no-op
        # that still printed "no issues".
        with mock.patch.dict(sys.modules, {'crm_api.models': None}):
            errors = check_production_roles_match_the_model(None)
        self.assertEqual([e.id for e in errors], ['core.E010'])


class EntitlementTests(SimpleTestCase):

    def test_absent_key_means_enabled(self):
        # Sparse storage: a module added to the registry must not switch itself
        # off for every existing boutique the moment it is deployed.
        self.assertTrue(is_enabled({}, 'inventory'))
        self.assertTrue(is_enabled({'tailors': False}, 'inventory'))
        self.assertTrue(is_enabled(None, 'inventory'))
        self.assertFalse(is_enabled({'inventory': False}, 'inventory'))

    def test_longest_prefix_wins(self):
        self.assertEqual(module_for_path('/api/inventory/catalog/'), 'inventory_catalog')
        self.assertEqual(module_for_path('/api/inventory/items/'), 'inventory')
        self.assertEqual(module_for_path('/api/order-drafts/'), 'order_drafts')
        self.assertEqual(module_for_path('/api/email/send/'), 'email')

    def test_ungoverned_path_is_allowed(self):
        self.assertIsNone(module_for_path('/api/orders/'))
        self.assertIsNone(module_for_path('/api/auth/me/'))


class DistributionTests(SimpleTestCase):

    def test_absent_key_means_the_role_default(self):
        self.assertTrue(role_allows({}, 'Tailor', 'notifications'))
        self.assertFalse(role_allows({}, 'Tailor', 'payroll'))
        self.assertTrue(role_allows({'Tailor': {}}, 'Tailor', 'notifications'))

    def test_explicit_beats_default_both_ways(self):
        self.assertTrue(role_allows({'Tailor': {'payroll': True}}, 'Tailor', 'payroll'))
        self.assertFalse(
            role_allows({'Tailor': {'notifications': False}}, 'Tailor', 'notifications'))

    def test_owner_is_always_allowed(self):
        # An owner who could switch off their own Inventory would have no
        # screen left to switch it back on.
        self.assertTrue(role_allows({'Owner': {'inventory': False}}, 'Owner', 'inventory'))
        self.assertNotIn('Owner', ROLE_DEFAULTS)
        self.assertEqual(effective_modules({}, {'Owner': {'inventory': False}}, 'Owner'),
                         sorted(MODULES))

    def test_unknown_role_gets_the_tailor_defaults(self):
        for role in (None, 'Marketing Lead', '', 0):
            with self.subTest(role=role):
                self.assertEqual(effective_modules({}, {}, role), sorted(TAILOR_DEFAULT))
                self.assertLess(len(effective_modules({}, {}, role)), len(MODULES))

    def test_designer_is_confined_to_design(self):
        # core/permissions.py RolePermission already denies a designer every
        # business endpoint; this must not be a second, looser answer.
        self.assertEqual(effective_modules({}, {}, 'Designer'), sorted(ROLE_DEFAULTS['Designer']))
        self.assertNotIn('inventory', ROLE_DEFAULTS['Designer'])
        self.assertNotIn('staff', ROLE_DEFAULTS['Designer'])

    def test_specialists_are_tailor_shaped(self):
        for role in PRODUCTION_ROLES:
            if role == 'Master':
                continue
            with self.subTest(role=role):
                self.assertEqual(ROLE_DEFAULTS[role], TAILOR_DEFAULT)
        self.assertLess(TAILOR_DEFAULT, ROLE_DEFAULTS['Master'])

    def test_malformed_role_modules_does_not_raise(self):
        # The column is JSON written through an API. Anything can be in it, and
        # this runs inside a permission class on every request.
        for junk in ([], 'inventory', 42, None, {'Tailor': []}, {'Tailor': 'all'}):
            with self.subTest(junk=junk):
                self.assertTrue(role_allows(junk, 'Tailor', 'notifications'))
                self.assertFalse(role_allows(junk, 'Tailor', 'payroll'))
                self.assertTrue(role_allows(junk, 'Owner', 'payroll'))


class TwoLayerTests(SimpleTestCase):

    def test_entitlement_beats_distribution(self):
        off = {'inventory': False}
        self.assertNotIn('inventory', effective_modules(off, {}, 'Owner'))
        self.assertNotIn(
            'inventory', effective_modules(off, {'Master': {'inventory': True}}, 'Master'))

    def test_distribution_narrows_an_entitled_module(self):
        self.assertIn('activities', effective_modules({}, {}, 'Master'))
        self.assertNotIn(
            'activities', effective_modules({}, {'Master': {'activities': False}}, 'Master'))

    def test_effective_modules_is_sorted_and_a_subset(self):
        modules = effective_modules({}, {}, 'Master')
        self.assertEqual(modules, sorted(modules))
        self.assertLessEqual(set(modules), set(MODULES))


class CatalogueTests(SimpleTestCase):

    def test_existing_keys_survive(self):
        # superadmin/api_views.py and the console frontend read these.
        data = catalogue()
        self.assertEqual(
            set(data), {'modules', 'groups', 'structural', 'client_only', 'always_on'})
        first = data['modules'][0]
        self.assertEqual(
            set(first), {'key', 'label', 'prefixes', 'description', 'gateable', 'group'})

    def test_every_module_carries_its_group(self):
        for entry in catalogue()['modules']:
            with self.subTest(module=entry['key']):
                self.assertEqual(entry['group'], MODULE_GROUP[entry['key']])
                self.assertIn(entry['group'], catalogue()['groups'])

    def test_all_roles_covers_owner_designer_and_the_floor(self):
        # Owner, Designer, and the six the boutique kept: Master, Tailor,
        # Maggam Master, Karigar, Packaging Staff, QC Staff.
        self.assertEqual(len(ALL_ROLES), 8)
        self.assertEqual(set(ALL_ROLES), {'Owner', 'Designer'} | set(PRODUCTION_ROLES))


def _view(request):
    return HttpResponse()


#: A fake URLconf, used only by the ROOT_URLCONF-overriding tests above. This
#: is what the next Marketing module looks like on the day it lands -- in each
#: of the shapes it could land in, because the walk has to survive all of them.
urlpatterns = [
    # Children carry the literal segments.
    path('api/marketing/', include([path('campaigns/', _view)])),
    # The app answers on its own mount point and adds nothing under it.
    path('api/marketing-b/', include([path('', _view)])),
    # Mixed: a root view AND a child route.
    path('api/marketing-c/', include([path('', _view), path('reports/', _view)])),
    # The bus. Governed by nothing, carries a root view and its format twin
    # the way crm_api's DefaultRouter does, and must be opened up not judged.
    path('api/', include([
        path('', _view),
        re_path(r'^\.(?P<format>[a-z0-9]+)/?$', _view),
        path('orders/', _view),
    ])),
    # Quiet neighbours: one a module governs, one always-on with children
    # under it that must not be walked.
    path('api/tailors/', _view),
    path('admin/', include([path('login/', _view)])),
]
