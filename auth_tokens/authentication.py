"""Access tokens that stop working.

DRF's TokenAuthentication has no notion of age: a key it accepts today it
accepts forever, and this product handed those keys to a phone. Everything else
about the scheme is kept -- the header, the model, the tenant-scoped table --
because a thousand tests, two frontends and every deployed client already speak
it.

The refusal carries a `code`, which is the part the Android app and the browser
both depend on: `token_expired` means "spend your refresh token and retry",
while a plain 401 means "sign in again". Without that distinction a client
cannot tell a stale minute from a revoked session, and the only safe reading of
an ambiguous 401 is the one that throws the user back to the login screen.
"""

from datetime import timedelta

from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .services import access_ttl


class ExpiringTokenAuthentication(TokenAuthentication):
    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        if token.created + timedelta(seconds=access_ttl()) <= timezone.now():
            raise AuthenticationFailed(
                {'detail': 'Your session has expired.', 'code': 'token_expired'})
        return user, token
