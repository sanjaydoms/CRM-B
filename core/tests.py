"""Tests for the one place a user's role is decided.

The fallback here has been wrong twice already -- once when "no Tailor
profile" was read as Owner and locked owners out of their own workflow, and
again when the same fallback would have handed a designer-only account full
Owner access the moment designers got logins. Both were the same bug shape:
treating "the lookup I tried came back empty" as proof rather than as one
possibility among several.
"""

from django.contrib.auth.models import User
from django_tenants.test.cases import TenantTestCase

from apps.design_studio.models import Designer
from core.roles import DESIGNER, OWNER, resolve_user_role
from crm_api.models import Tailor


class ResolveUserRoleTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@roles.test"
        tenant.name = "Roles Test Boutique"
        return tenant

    def setUp(self):
        super().setUp()
        from django.db import connection
        connection.set_tenant(self.tenant)

    def test_anonymous_has_no_role(self):
        self.assertIsNone(resolve_user_role(None))

        class Anonymous:
            is_authenticated = False
        self.assertIsNone(resolve_user_role(Anonymous()))

    def test_superuser_is_owner_regardless_of_profile(self):
        boss = User.objects.create_superuser(
            username="boss@roles.test", email="boss@roles.test", password="x")
        self.assertEqual(resolve_user_role(boss), OWNER)

    def test_a_tailor_profile_reports_its_own_role(self):
        user = User.objects.create_user(username="tailor@roles.test", password="x")
        Tailor.objects.create(name="Ravi", specialty="Bridal", role="Master", user=user)
        self.assertEqual(resolve_user_role(user), "Master")

    def test_a_designer_profile_reports_designer(self):
        user = User.objects.create_user(username="designer@roles.test", password="x")
        Designer.objects.create(name="Priya", user=user)
        self.assertEqual(resolve_user_role(user), DESIGNER)

    def test_no_profile_at_all_falls_back_to_owner(self):
        # The genuine case this fallback exists for: the boutique owner's own
        # account, created at signup, which never gets a Tailor or Designer row.
        user = User.objects.create_user(username="plain@roles.test", password="x")
        self.assertEqual(resolve_user_role(user), OWNER)

    def test_a_tailor_profile_wins_over_a_designer_profile(self):
        # Someone who both stitches and designs is not ambiguous: the account
        # that does production work is treated as staff first, since that is
        # the profile the workflow engine's stage assignment actually reads.
        user = User.objects.create_user(username="both@roles.test", password="x")
        Tailor.objects.create(name="Anita", specialty="Bridal", role="Tailor", user=user)
        Designer.objects.create(name="Anita", user=user)
        self.assertEqual(resolve_user_role(user), "Tailor")

    def test_a_designer_only_account_is_never_reported_as_owner(self):
        # This is the fix. Before it, a Designer with no Tailor profile
        # fell through the same branch as the boutique owner's own account and
        # was handed full Owner access -- the exact failure the module's
        # permission matrix promises never happens.
        user = User.objects.create_user(username="designer2@roles.test", password="x")
        Designer.objects.create(name="Ravi", user=user)
        self.assertNotEqual(resolve_user_role(user), OWNER)
        self.assertEqual(resolve_user_role(user), DESIGNER)
