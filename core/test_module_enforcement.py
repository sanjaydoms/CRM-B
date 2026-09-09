"""The role layer, proved over real HTTP.

These tests exist because the interesting failures of a permission class are
not unit failures. `ModuleAccess.has_permission` returning False in isolation
proves nothing about whether the ~21 views that declare their own
permission_classes ever call it, whether the middleware's entitlement refusal
still comes first, or whether a boutique with no BoutiqueSettings row 500s on
every request. So every case below goes through the full stack: middleware,
tenant schema, token auth, router, permission class.

The tenant fixtures are tenants/tests.py's -- temporary_tenant creates the
schema and drops it, set_modules writes enabled_modules and clears the
middleware cache that would otherwise serve the old answer.
"""

from django.contrib.auth.models import User
from django.db import connection
from django.urls import get_resolver
from django_tenants.utils import schema_context
from django.test import TransactionTestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.modules import MODULES, module_for_path
from core.permissions import ModuleAccess
from crm_api.models import BoutiqueSettings, Tailor
from tenants.tests import set_modules, temporary_tenant


def _client(schema, email):
    """A signed-in APIClient for `email` in `schema`, by token, like the app."""
    with schema_context(schema):
        user, _ = User.objects.get_or_create(
            username=email, defaults={'email': email})
        if (user.email or '') != email:
            user.email = email
            user.save(update_fields=['email'])
        key = Token.objects.get_or_create(user=user)[0].key
    connection.set_schema_to_public()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION='Token ' + key, HTTP_X_TENANT_ID=schema)
    return client


def _tailor(schema, email, role='Tailor'):
    with schema_context(schema):
        user, _ = User.objects.get_or_create(
            username=email, defaults={'email': email})
        Tailor.objects.get_or_create(
            user=user, defaults={'name': email, 'specialty': 'Blouse', 'role': role})
    return _client(schema, email)


def _designer(schema, email):
    from apps.design_studio.models import Designer

    with schema_context(schema):
        user, _ = User.objects.get_or_create(
            username=email, defaults={'email': email})
        Designer.objects.get_or_create(user=user, defaults={'name': email})
    return _client(schema, email)


def _set_role_modules(schema, role_modules):
    with schema_context(schema):
        BoutiqueSettings.objects.update_or_create(
            id=1, defaults={'role_modules': role_modules})


def _message(response):
    """The refusal text, whichever layer wrote it.

    The middleware answers with JsonResponse {"error": ...}; DRF answers with
    {"detail": ...}. A test that reads only one of them silently passes when
    the wrong layer refuses.
    """
    body = response.json()
    return body.get('detail') or body.get('error') or ''


class RoleGateTests(TransactionTestCase):

    def test_a_tailor_is_refused_payroll_and_the_message_names_the_module(self):
        with temporary_tenant('rg_payroll', 'owner@rg.test', 'Atelier'):
            client = _tailor('rg_payroll', 'tailor@rg.test')

            response = client.get('/api/payroll/records/')

            self.assertEqual(response.status_code, 403)
            message = _message(response)
            # Naming the module is the point: three different 403s can reach a
            # caller here -- suspended boutique, module off for the boutique,
            # module not given to the role -- and a support call cannot tell
            # them apart from "Forbidden".
            self.assertIn('Payroll', message)
            self.assertIn('role', message)
            self.assertNotIn('switched off', message)
            self.assertNotIn('suspended', message)
            # PayrollRecordViewSet carries OwnerOrOwnFinancialRecord, which
            # allows every safe method to every signed-in role. If the gate had
            # not run first this would have been a 200 with the boutique's
            # payslips in it.
            self.assertNotIn('Only the boutique owner', message)

    def test_the_same_tailor_still_reaches_their_own_work(self):
        with temporary_tenant('rg_work', 'owner@rg.test', 'Atelier'):
            client = _tailor('rg_work', 'tailor@rg.test')

            # Orders are STRUCTURAL -- module_for_path returns None and the
            # gate must not touch them. Notifications are governed and every
            # role keeps them, because the bell is on every screen.
            self.assertEqual(client.get('/api/orders/').status_code, 200)
            self.assertEqual(client.get('/api/notifications/').status_code, 200)

    def test_a_view_with_its_own_permission_classes_is_gated_too(self):
        """StaffProfileViewSet declares permission_classes = [StaffSelfOrOwner].

        That replaces DEFAULT_PERMISSION_CLASSES outright, so a gate added only
        to the default would do nothing here. StaffSelfOrOwner allows every
        safe method to every role, so a Tailor's GET is a 200 unless the module
        gate composed into the class itself refuses it first.

        The switch is explicit rather than default because ROLE_DEFAULTS keeps
        `staff` on for production roles on purpose -- it is where a tailor
        checks themselves in and out (see core/modules.py). Turning it off for
        the role is exactly the owner's decision this layer exists to carry.
        """
        with temporary_tenant('rg_staff', 'owner@rg.test', 'Atelier'):
            client = _tailor('rg_staff', 'tailor@rg.test')
            self.assertEqual(client.get('/api/staff/profiles/').status_code, 200)

            _set_role_modules('rg_staff', {'Tailor': {'staff': False}})

            response = client.get('/api/staff/profiles/')
            self.assertEqual(response.status_code, 403)
            self.assertIn('Staff Management', _message(response))

    def test_the_owner_reaches_every_module_the_boutique_is_entitled_to(self):
        with temporary_tenant('rg_owner', 'owner@rg.test', 'Atelier'):
            # The owner is not in ROLE_DEFAULTS at all, and switching a module
            # off for "Owner" must not take it away -- an owner locked out of
            # Boutique Settings has no way back in.
            _set_role_modules('rg_owner', {'Owner': {k: False for k in MODULES}})
            client = _client('rg_owner', 'owner@rg.test')

            refused = []
            for key, (_label, prefixes, _d) in MODULES.items():
                for prefix in prefixes:
                    if prefix.startswith('/track/'):
                        continue  # public link, no sign-in, no role
                    if client.get(prefix).status_code == 403:
                        refused.append(f'{key} -> {prefix}')
            self.assertEqual(refused, [])

    def test_a_designer_reaches_the_studio_and_is_refused_inventory(self):
        with temporary_tenant('rg_design', 'owner@rg.test', 'Atelier'):
            client = _designer('rg_design', 'designer@rg.test')

            self.assertEqual(client.get('/api/design-studio/assets/').status_code, 200)

            response = client.get('/api/inventory/items/')
            self.assertEqual(response.status_code, 403)
            self.assertIn('Inventory', _message(response))

    def test_the_design_library_create_shortcut_does_not_escape_the_gate(self):
        """DesignLibraryPermission.has_role_permission returns True for
        `create` without consulting its parent at all. That branch is why the
        gate cannot live in a mixin below these classes: the subclass method
        would be found first and the mixin never called. Here the gate runs in
        has_permission, above every one of those shortcuts.

        A 400 instead of a 403 would mean the request reached serializer
        validation, i.e. past the permission layer.
        """
        with temporary_tenant('rg_dslib', 'owner@rg.test', 'Atelier'):
            client = _designer('rg_dslib', 'designer@rg.test')
            _set_role_modules('rg_dslib', {'Designer': {'design_studio': False}})

            response = client.post('/api/design-studio/assets/', {}, format='json')
            self.assertEqual(response.status_code, 403)
            self.assertIn('Design Studio', _message(response))

    def test_entitlement_beats_role_even_for_the_owner(self):
        with temporary_tenant('rg_layers', 'owner@rg.test', 'Atelier') as tenant:
            client = _client('rg_layers', 'owner@rg.test')
            self.assertEqual(client.get('/api/inventory/items/').status_code, 200)

            set_modules(tenant, {'inventory': False})

            response = client.get('/api/inventory/items/')
            self.assertEqual(response.status_code, 403)
            # The layers compose one way round only. role_allows says True for
            # the owner on everything; the boutique not having bought the
            # module still wins, and says so in the entitlement's words.
            self.assertIn('switched off', _message(response))
            self.assertIn('Inventory', _message(response))

    def test_a_boutique_with_no_settings_row_falls_back_to_the_defaults(self):
        with temporary_tenant('rg_bare', 'owner@rg.test', 'Atelier'):
            with schema_context('rg_bare'):
                self.assertEqual(BoutiqueSettings.objects.count(), 0)

            tailor = _tailor('rg_bare', 'tailor@rg.test')
            owner = _client('rg_bare', 'owner@rg.test')

            # No row is not "no rules" and it is not a 500 either: the map is
            # absent, so ROLE_DEFAULTS answers.
            refused = tailor.get('/api/payroll/records/')
            self.assertEqual(refused.status_code, 403)
            self.assertIn('Payroll', _message(refused))
            self.assertEqual(tailor.get('/api/orders/').status_code, 200)
            self.assertEqual(owner.get('/api/payroll/records/').status_code, 200)

            with schema_context('rg_bare'):
                self.assertEqual(BoutiqueSettings.objects.count(), 0)

    def test_a_malformed_role_map_falls_back_instead_of_raising(self):
        with temporary_tenant('rg_junk', 'owner@rg.test', 'Atelier'):
            # JSONField takes whatever the API wrote. A list where a dict was
            # expected must read as "nothing explicit", not as a 500 on every
            # request the class guards.
            _set_role_modules('rg_junk', ['not', 'a', 'map'])
            client = _tailor('rg_junk', 'tailor@rg.test')

            self.assertEqual(client.get('/api/notifications/').status_code, 200)
            self.assertEqual(client.get('/api/payroll/records/').status_code, 403)

            _set_role_modules('rg_junk', {'Tailor': 'yes please'})
            self.assertEqual(client.get('/api/notifications/').status_code, 200)
            self.assertEqual(client.get('/api/payroll/records/').status_code, 403)


class GateCompositionTests(TransactionTestCase):
    """Structural proofs, so the HTTP tests above cannot pass by luck.

    A permission class that re-defines has_permission, or a new governed view
    that declares a permission class from outside this hierarchy, would bypass
    the gate without failing a single request-level test for a module that
    happens to be on by default.
    """

    def test_no_permission_class_redefines_has_permission(self):
        escapees = [f'{cls.__module__}.{cls.__qualname__}'
                    for cls in _gate_subclasses()
                    if cls.has_permission is not ModuleAccess.has_permission]
        self.assertEqual(
            escapees, [],
            'has_permission is final on ModuleAccess -- put the rule in '
            'has_role_permission, or these classes silently skip the module '
            'gate:\n' + '\n'.join(escapees))

    def test_every_governed_view_declares_a_gated_permission_class(self):
        ungated = []
        for pattern, prefix in _routes():
            if module_for_path(prefix) is None:
                continue  # not governed -- nothing to enforce
            view = (getattr(pattern.callback, 'cls', None)
                    or getattr(pattern.callback, 'view_class', None))
            if view is None:
                continue  # a plain Django view, e.g. /track/: no DRF layer
            classes = getattr(view, 'permission_classes', [])
            if not any(isinstance(c, type) and issubclass(c, ModuleAccess)
                       for c in classes):
                ungated.append(f'{prefix} -> {view.__name__} has {classes}')
        self.assertEqual(
            ungated, [],
            'Governed routes whose permission_classes contain nothing derived '
            'from ModuleAccess. Add ModuleAccess to the list:\n'
            + '\n'.join(ungated))


def _gate_subclasses():
    """Every loaded ModuleAccess subclass, wherever in the project it lives.

    Discovered rather than listed. This scanned two hard-coded modules
    (core.permissions and apps.design_studio.permissions), so a subclass added
    in any third file -- another apps/*/permissions.py, or one defined next to
    the view it guards -- escaped this test AND
    test_every_governed_view_declares_a_gated_permission_class, which only asks
    whether the class derives from ModuleAccess, not whether it still calls the
    gate. A class that does both is exactly the bypass this pair is supposed to
    make impossible.

    get_resolver().url_patterns first: __subclasses__ only knows about classes
    that have been imported, and loading the urlconf imports every view module,
    which imports every permission class any route can actually use. One that
    nothing imports cannot guard anything.
    """
    get_resolver().url_patterns
    found, stack = [], list(ModuleAccess.__subclasses__())
    while stack:
        cls = stack.pop()
        if cls not in found:
            found.append(cls)
            stack.extend(cls.__subclasses__())
    return found


def _routes(resolver=None, prefix='/'):
    """(pattern, concrete-enough url) for every leaf route in the tenant urlconf.

    module_for_path only reads the prefix, so an unsubstituted `<pk>` at the
    tail does not change the answer -- no need for the placeholder-filling
    machinery superadmin/test_api_security.py needs for real requests.
    """
    from django.urls import URLPattern, URLResolver

    resolver = resolver or get_resolver()
    for entry in resolver.url_patterns:
        here = prefix + str(entry.pattern).lstrip('^')
        if isinstance(entry, URLResolver):
            yield from _routes(entry, here)
        elif isinstance(entry, URLPattern):
            yield entry, here
