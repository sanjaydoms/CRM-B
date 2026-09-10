"""The owner's role/module switchboard: /api/boutique-settings/role-modules/.

Layer 2 of the access contract. Layer 1 (has the boutique BOUGHT Inventory?)
belongs to the platform console and TenantHeaderMiddleware and is tested in
tenants/tests.py. This file only covers the layer the boutique owner controls:
of what we have, who on the floor sees it.
"""

from django.contrib.auth.models import User
from django.test import TransactionTestCase
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.design_studio.models import Designer
from core.modules import ALL_ROLES, MODULES, effective_modules
from crm_api.models import BoutiqueSettings, Tailor


class RoleModuleBase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@rolemodules.test"
        tenant.name = "Role Modules Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        from django.db import connection
        connection.set_tenant(self.tenant)

        self.url = reverse('boutique-settings-role-modules')

        self.owner = User.objects.create_user(
            username="owner@rolemodules.test", email="owner@rolemodules.test",
            password="ownerpass123")

        # A real colleague on each side of the gate, not an anonymous caller.
        # The point is that somebody legitimately signed in still cannot read
        # or edit the map that decides what they see.
        self.tailor_user = User.objects.create_user(
            username="ravi@rolemodules.test", password="tailorpass123")
        Tailor.objects.create(name='Ravi', specialty='Blouses', role='Tailor',
                              user=self.tailor_user)
        self.designer_user = User.objects.create_user(
            username="priya@rolemodules.test", password="designerpass123")
        Designer.objects.create(name='Priya', user=self.designer_user)

    def client_for(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Token {token.key}',
                        HTTP_X_TENANT_ID=self.tenant.schema_name)
        return api

    def patch(self, user, role_modules):
        return self.client_for(user).patch(
            self.url, {'role_modules': role_modules}, format='json')


class OwnerCanDistributeTests(RoleModuleBase):

    def test_the_owner_reads_the_whole_map(self):
        response = self.client_for(self.owner).get(self.url)
        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.data['roles'], list(ALL_ROLES))
        self.assertEqual(sorted(response.data['effective']), sorted(ALL_ROLES))
        self.assertEqual({m['key'] for m in response.data['modules']}, set(MODULES))
        # Every module carries its group, so the screen can lay the switches
        # out the way the navigation is laid out.
        self.assertTrue(all(m['group'] in response.data['groups']
                            for m in response.data['modules']))

    def test_the_owner_writes_a_role_off_and_it_comes_back(self):
        response = self.patch(self.owner, {'Tailor': {'inventory': False}})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['role_modules']['Tailor']['inventory'], False)
        self.assertNotIn('inventory', response.data['effective']['Tailor'])

        stored = BoutiqueSettings.objects.get(id=1).role_modules
        self.assertEqual(stored, {'Tailor': {'inventory': False}})

    def test_the_owner_keeps_every_entitled_module_whatever_is_stored(self):
        """The owner distributes; the owner is never on the receiving end.

        Storing an Owner row is refused outright (below), but the map can also
        be edited by hand or by an older client, so the read path must not be
        the only thing standing between an owner and a locked-out console.
        """
        self.patch(self.owner, {'Tailor': {'inventory': False}})
        response = self.client_for(self.owner).get(self.url)
        self.assertEqual(sorted(response.data['effective']['Owner']),
                         sorted(response.data['entitled']))


class OnlyTheOwnerTests(RoleModuleBase):

    def test_a_tailor_is_refused_both_verbs(self):
        api = self.client_for(self.tailor_user)
        self.assertEqual(api.get(self.url).status_code, 403)
        self.assertEqual(self.patch(self.tailor_user,
                                    {'Tailor': {'inventory': True}}).status_code, 403)

    def test_a_designer_is_refused_both_verbs(self):
        api = self.client_for(self.designer_user)
        self.assertEqual(api.get(self.url).status_code, 403)
        self.assertEqual(self.patch(self.designer_user,
                                    {'Tailor': {'inventory': True}}).status_code, 403)

    def test_a_refused_read_writes_nothing(self):
        self.patch(self.tailor_user, {'Tailor': {'inventory': True}})
        self.assertEqual(BoutiqueSettings.objects.filter(id=1).count(), 0)

    def test_the_map_is_not_served_on_the_general_settings_body(self):
        """/api/boutique-settings/ is ALWAYS_ON and everybody reads it.

        `fields = '__all__'` would have published role_modules there the moment
        the field landed, handing the map to the roles it restricts.
        """
        self.patch(self.owner, {'Tailor': {'inventory': False}})
        response = self.client_for(self.tailor_user).get(
            reverse('boutique-settings-list'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('role_modules', response.data)


class RejectedWritesTests(RoleModuleBase):

    def assert_400_naming(self, response, needle):
        self.assertEqual(response.status_code, 400)
        self.assertIn(needle, str(response.data))

    def test_an_unknown_role_is_refused_and_named(self):
        self.assert_400_naming(
            self.patch(self.owner, {'Tailer': {'inventory': False}}), 'Tailer')
        self.assertEqual(BoutiqueSettings.objects.get(id=1).role_modules, {})

    def test_an_unknown_module_is_refused_and_named(self):
        self.assert_400_naming(
            self.patch(self.owner, {'Tailor': {'inventry': False}}), 'inventry')

    def test_a_non_boolean_switch_is_refused(self):
        self.assert_400_naming(
            self.patch(self.owner, {'Tailor': {'inventory': 'no'}}), 'inventory')

    def test_the_owner_role_cannot_be_stored_at_all(self):
        response = self.patch(self.owner, {'Owner': {'inventory': False}})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(BoutiqueSettings.objects.get(id=1).role_modules, {})

    def test_a_bad_shape_is_refused(self):
        self.assertEqual(self.patch(self.owner, ['Tailor']).status_code, 400)
        self.assertEqual(self.patch(self.owner, {'Tailor': True}).status_code, 400)


class MergeTests(RoleModuleBase):

    def test_a_partial_patch_merges_rather_than_replaces(self):
        """Two owners on the settings screen, each editing a different role.

        A replace would let whichever saved second silently delete the other's
        work, and both screens would show it as saved.
        """
        self.patch(self.owner, {'Tailor': {'inventory': False}})
        self.patch(self.owner, {'QC Staff': {'payroll': False}})
        response = self.patch(self.owner, {'Tailor': {'fabrics': False}})

        self.assertEqual(response.data['role_modules'], {
            'Tailor': {'inventory': False, 'fabrics': False},
            'QC Staff': {'payroll': False},
        })

    def test_a_later_patch_overwrites_the_same_key(self):
        self.patch(self.owner, {'Tailor': {'inventory': False}})
        response = self.patch(self.owner, {'Tailor': {'inventory': True}})
        self.assertEqual(response.data['role_modules']['Tailor']['inventory'], True)
        self.assertIn('inventory', response.data['effective']['Tailor'])


class UnconfiguredBoutiqueTests(RoleModuleBase):

    def test_the_field_defaults_to_empty_on_a_fresh_boutique(self):
        self.assertEqual(BoutiqueSettings.objects.create(id=1).role_modules, {})

    def test_an_untouched_boutique_behaves_exactly_as_it_did_before(self):
        """The migration is an AddField with default={}, so nothing moves.

        An existing boutique has made no distribution decisions, and every role
        must therefore see precisely what ROLE_DEFAULTS gives it -- not more,
        and not "nothing until the owner ticks something".
        """
        BoutiqueSettings.objects.get_or_create(id=1)
        response = self.client_for(self.owner).get(self.url)

        self.assertEqual(response.data['role_modules'], {})
        self.assertEqual(response.data['effective'],
                         {role: effective_modules({}, {}, role) for role in ALL_ROLES})


class EntitlementTests(RoleModuleBase):

    def test_an_unentitled_module_is_configurable_but_marked(self):
        """The boutique may buy Inventory next month.

        So the switch stays editable -- but the response says the module is not
        entitled, because a switch that looks live and changes nothing is worse
        than one shown as unavailable.
        """
        # The existing helper, not a hand-rolled update: it switches to the
        # public schema and clears the middleware's tenant cache, and forgetting
        # either leaves the request reading the boutique it had five minutes ago.
        from django.db import connection
        from tenants.middleware import clear_tenant_cache
        from tenants.tests import set_modules
        set_modules(self.tenant, {'inventory': False})
        # set_modules leaves the connection on the public schema, and auth_user
        # is a TENANT table -- issuing the owner's token from here would write
        # it into the wrong schema and fail on the foreign key.
        connection.set_tenant(self.tenant)
        self.addCleanup(clear_tenant_cache)

        response = self.patch(self.owner, {'Tailor': {'inventory': True}})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('inventory', response.data['entitled'])
        by_key = {m['key']: m for m in response.data['modules']}
        self.assertFalse(by_key['inventory']['entitled'])
        # Entitlement wins over distribution: an explicit yes from the owner
        # cannot conjure a module the boutique has not got.
        self.assertNotIn('inventory', response.data['effective']['Tailor'])


class OneRowTests(RoleModuleBase):
    """/auth/me/ and the permission class must read the SAME settings row.

    The payload decides what the navigation offers; core.permissions decides
    what the request may touch. They disagreed about WHICH row holds the map:
    auth_views read `.first()` (Django orders that by pk) while the gate, the
    owner screen and every other reader pin id=1.

    Nothing in the schema makes those the same row. BoutiqueSettings has no
    unique constraint and no singleton save(), so a second row can exist; the
    API only ever writes id=1, which means a stray row arrives from a fixture,
    a restored dump or a psql session -- precisely when nobody is watching.
    """

    def gate_reads(self):
        from types import SimpleNamespace

        from core.permissions import _role_modules as gate
        # The gate caches on the request object; a bare namespace is a request
        # as far as it is concerned, and a fresh one per call means no stale
        # cache is doing the answering.
        return gate(SimpleNamespace())

    def payload_reads(self):
        from crm_api.auth_views import _role_modules as payload
        return payload()

    def test_a_stray_row_is_not_mistaken_for_the_map(self):
        BoutiqueSettings.objects.create(
            id=2, role_modules={'Tailor': {'inventory': False}})

        # No row 1: no decisions recorded, so ROLE_DEFAULTS answers -- and both
        # sides say so. Reading the stray row here would have hidden Inventory
        # from every tailor's navigation while the gate kept letting them in.
        self.assertEqual(self.payload_reads(), {})
        self.assertEqual(self.payload_reads(), self.gate_reads())

    def test_row_one_wins_over_a_stray_row(self):
        BoutiqueSettings.objects.create(
            id=1, role_modules={'Tailor': {'inventory': False}})
        BoutiqueSettings.objects.create(
            id=2, role_modules={'Tailor': {'inventory': True, 'payroll': False}})

        self.assertEqual(self.payload_reads(), {'Tailor': {'inventory': False}})
        self.assertEqual(self.payload_reads(), self.gate_reads())

    def test_what_the_owner_saves_is_what_both_sides_read(self):
        self.patch(self.owner, {'Tailor': {'inventory': False}})

        self.assertEqual(self.payload_reads(), {'Tailor': {'inventory': False}})
        self.assertEqual(self.payload_reads(), self.gate_reads())

    def test_a_corrupt_column_reads_as_no_decisions_on_both_sides(self):
        BoutiqueSettings.objects.create(id=1, role_modules=['nonsense'])

        self.assertEqual(self.payload_reads(), {})
        self.assertEqual(self.gate_reads(), {})


class CorruptColumnTests(RoleModuleBase):
    """The owner's PATCH is the only way back, so it must survive the mess.

    core.modules.role_allows and core.permissions both refuse to assume the
    column holds a dict, and heal anything else to "no decisions recorded".
    The write path assumed it anyway -- dict(config.role_modules or {}) and
    {**(stored.get(role) or {})} -- and 500'd, which left psql as the only
    repair tool for the one screen whose entire job is repairing this.
    """

    def corrupt(self, value):
        BoutiqueSettings.objects.update_or_create(
            id=1, defaults={'role_modules': value})

    def test_a_column_holding_a_list_is_repairable_from_the_screen(self):
        self.corrupt(['Tailor'])
        response = self.patch(self.owner, {'Tailor': {'inventory': False}})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(BoutiqueSettings.objects.get(id=1).role_modules,
                         {'Tailor': {'inventory': False}})

    def test_a_column_holding_a_string_is_repairable_from_the_screen(self):
        self.corrupt('everything')
        response = self.patch(self.owner, {'Tailor': {'inventory': False}})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(BoutiqueSettings.objects.get(id=1).role_modules,
                         {'Tailor': {'inventory': False}})

    def test_one_bad_role_entry_does_not_take_the_healthy_ones_with_it(self):
        self.corrupt({'Tailor': 'everything', 'QC Staff': {'payroll': False}})
        response = self.patch(self.owner, {'Tailor': {'inventory': False}})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(BoutiqueSettings.objects.get(id=1).role_modules, {
            'Tailor': {'inventory': False},
            'QC Staff': {'payroll': False},
        })

    def test_reading_a_corrupt_column_reports_no_decisions_rather_than_500(self):
        self.corrupt('everything')
        response = self.client_for(self.owner).get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['role_modules'], {})


class ConcurrentPatchTests(TransactionTestCase):
    """Two owners saving different roles at the same instant.

    The one test in this file with real transactions and a second connection.
    Every other test runs inside a single test transaction, where two
    "concurrent" PATCHes are just two sequential calls -- which is exactly why
    an unguarded read-modify-write on a JSON blob passed a whole suite of merge
    tests while dropping owners' decisions in production.

    The defect: the view read the row, merged the patch into what it read, and
    saved. A second request that committed in between was overwritten -- no
    error, and both screens showed the save as successful.
    """

    def test_a_patch_committing_mid_merge_is_not_overwritten(self):
        import threading
        import time

        from django.db import connection, transaction
        from django_tenants.utils import schema_context
        from tenants.tests import temporary_tenant

        with temporary_tenant('role_modules_race', 'owner@race.test',
                              'Race Atelier') as tenant:
            with schema_context(tenant.schema_name):
                owner = User.objects.create_user(
                    username='owner@race.test', email='owner@race.test',
                    password='racerpw12345')
                BoutiqueSettings.objects.create(id=1)
                key = Token.objects.create(user=owner).key

            holding = threading.Event()
            failures = []

            def first_owner():
                """Takes the row the way the view does, then commits QC Staff."""
                try:
                    with schema_context(tenant.schema_name), transaction.atomic():
                        BoutiqueSettings.objects.select_for_update().get(id=1)
                        holding.set()
                        # ponytail: half a second, rather than instrumenting the
                        # view to signal exactly when it reads. A machine too
                        # slow to get the request to the row in that window
                        # makes this test pass for the wrong reason -- it can
                        # never make it fail for one.
                        time.sleep(0.5)
                        BoutiqueSettings.objects.filter(id=1).update(
                            role_modules={'QC Staff': {'payroll': False}})
                except Exception as exc:        # noqa: BLE001 - asserted below
                    failures.append(exc)
                finally:
                    connection.close()

            thread = threading.Thread(target=first_owner)
            thread.start()
            self.assertTrue(holding.wait(timeout=10),
                            'the first owner never took the row')

            api = APIClient()
            api.credentials(HTTP_AUTHORIZATION=f'Token {key}',
                            HTTP_X_TENANT_ID=tenant.schema_name)
            # The second owner arrives while the first still holds the row. It
            # reads once before the lock and must not merge onto that read: by
            # the time it is allowed to write, QC Staff is stored.
            response = api.patch(
                reverse('boutique-settings-role-modules'),
                {'role_modules': {'Tailor': {'inventory': False}}}, format='json')
            thread.join(timeout=30)

            self.assertEqual(failures, [])
            self.assertEqual(response.status_code, 200)
            with schema_context(tenant.schema_name):
                self.assertEqual(
                    BoutiqueSettings.objects.get(id=1).role_modules,
                    {'Tailor': {'inventory': False},
                     'QC Staff': {'payroll': False}},
                    'one owner\'s decision was overwritten by the other')
