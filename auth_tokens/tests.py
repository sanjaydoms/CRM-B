"""What a session is worth, and for how long.

The product used to answer "forever" to the second question. These tests are
the record that it no longer does, and -- more importantly -- that the machinery
which replaces it cannot be turned back into a permanent credential by replaying
an old refresh token.
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.db import connection
from django.test import override_settings
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from auth_tokens.models import RefreshToken
from auth_tokens.services import issue_session, revoke_all, rotate


class SessionTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@sessions.test"
        tenant.name = "Sessions Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        self.password = "ownerpass123"
        self.owner = User.objects.create_user(
            username="owner@sessions.test", email="owner@sessions.test",
            password=self.password)
        self.client = APIClient()

    def _as(self, key):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {key}',
                           HTTP_X_TENANT_ID=self.tenant.schema_name)
        return client

    def _refresh(self, raw):
        return self.client.post('/api/auth/refresh/', {'refresh': raw},
                                format='json',
                                HTTP_X_TENANT_ID=self.tenant.schema_name)

    # --- the access token now ages ---------------------------------------

    def test_a_fresh_access_token_works(self):
        session = issue_session(self.owner)
        self.assertEqual(self._as(session['token']).get('/api/auth/me/').status_code, 200)

    def test_an_aged_access_token_is_refused_and_says_why(self):
        session = issue_session(self.owner)
        # Reaching past the model rather than sleeping: `created` is auto_now_add,
        # so this is the only way to age one.
        Token.objects.filter(user=self.owner).update(
            created=timezone.now() - timedelta(seconds=7200))

        response = self._as(session['token']).get('/api/auth/me/')
        self.assertEqual(response.status_code, 401)
        # The code is the whole point: without it a client cannot tell "refresh
        # and retry" from "send the user back to the login screen".
        self.assertEqual(response.data['code'], 'token_expired')

    @override_settings(ACCESS_TOKEN_TTL=0)
    def test_ttl_is_a_setting_not_a_constant(self):
        session = issue_session(self.owner)
        self.assertEqual(self._as(session['token']).get('/api/auth/me/').status_code, 401)

    # --- refresh ----------------------------------------------------------

    def test_refresh_returns_a_working_session(self):
        session = issue_session(self.owner)
        Token.objects.filter(user=self.owner).update(
            created=timezone.now() - timedelta(seconds=7200))

        response = self._refresh(session['refresh'])
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.data['token'], session['token'])
        self.assertNotEqual(response.data['refresh'], session['refresh'])
        self.assertEqual(response.data['user']['role'], 'Owner')
        self.assertEqual(self._as(response.data['token']).get('/api/auth/me/').status_code, 200)

    def test_a_spent_refresh_token_cannot_be_spent_twice(self):
        session = issue_session(self.owner)
        self.assertEqual(self._refresh(session['refresh']).status_code, 200)

        replay = self._refresh(session['refresh'])
        self.assertEqual(replay.status_code, 401)
        self.assertEqual(replay.data['code'], 'refresh_invalid')

    def test_a_replay_ends_every_session_the_user_holds(self):
        """The reason rotation is worth having at all.

        A replayed refresh token means two parties hold one, and there is no way
        to tell from here which is the tailor and which is not. Ending both is
        the only answer that is safe in either case.
        """
        session = issue_session(self.owner)
        good = self._refresh(session['refresh'])
        live_refresh = good.data['refresh']

        self._refresh(session['refresh'])          # the replay

        self.assertEqual(self._refresh(live_refresh).status_code, 401)
        self.assertEqual(self._as(good.data['token']).get('/api/auth/me/').status_code, 401)

    def test_an_expired_refresh_token_is_refused(self):
        session = issue_session(self.owner)
        RefreshToken.objects.filter(user=self.owner).update(
            expires_at=timezone.now() - timedelta(seconds=1))
        self.assertIsNone(rotate(session['refresh']))

    def test_an_unknown_refresh_token_is_refused_without_a_500(self):
        self.assertEqual(self._refresh('not-a-token').status_code, 401)

    # --- the doors that end a session ------------------------------------

    def test_logout_kills_the_refresh_token_too(self):
        """Deleting only the access token left the longer-lived half live, so a
        signed-out session could mint itself a new one seconds later."""
        session = issue_session(self.owner)
        self.assertEqual(self._as(session['token']).post('/api/auth/logout/').status_code, 200)

        self.assertEqual(self._refresh(session['refresh']).status_code, 401)

    def test_signing_in_again_after_expiry_returns_a_usable_token(self):
        """The regression that expiry would otherwise have introduced.

        Login used get_or_create, which hands back the row that already exists
        -- `created` and all. Against an expiring token that means signing in
        with correct credentials and receiving a key that was already dead.
        """
        issue_session(self.owner)
        Token.objects.filter(user=self.owner).update(
            created=timezone.now() - timedelta(seconds=7200))

        response = APIClient().post(
            '/api/auth/login/',
            {'username': 'owner@sessions.test', 'password': self.password},
            format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('refresh', response.data)
        self.assertEqual(self._as(response.data['token']).get('/api/auth/me/').status_code, 200)

    def test_a_password_reset_revokes_the_refresh_token(self):
        """A reset exists to take a session away from whoever has it. Leaving
        the refresh half alive would hand it straight back."""
        session = issue_session(self.owner)
        self.owner.set_password('a-brand-new-password-123')
        self.owner.save(update_fields=['password'])
        revoke_all(self.owner)
        self.assertIsNone(rotate(session['refresh']))
