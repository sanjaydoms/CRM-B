"""Issuing, refreshing and revoking a session.

Every door that hands out credentials goes through `issue_session` -- boutique
sign-up, boutique login, and the platform console's login -- so there is one
definition of what a session is rather than three.

`Token.objects.get_or_create(user=...)` is what those three did before, and it
cannot survive an expiring access token: it returns the row that already exists,
`created` and all, so signing in again after an hour handed the caller a token
that was already dead. Every issue path here mints a fresh one.
"""

from django.conf import settings
from django.utils import timezone
from rest_framework.authtoken.models import Token

from .models import RefreshToken, hash_key


def access_ttl():
    return int(getattr(settings, 'ACCESS_TOKEN_TTL', 3600))


def refresh_ttl():
    return int(getattr(settings, 'REFRESH_TOKEN_TTL', 30 * 24 * 3600))


def issue_access(user):
    """A brand-new access token, replacing any the user already held.

    Deleting first is what makes `created` -- which is the expiry clock, since
    DRF's Token has no other timestamp -- mean "issued now".

    The consequence, stated plainly because it is easy to miss: DRF's Token is
    keyed on the user, so there is one access token per person, and EVERY issue
    -- a sign-in or a refresh -- replaces it. Two devices belonging to the same
    person therefore evict each other's access token.

    They do not evict each other's SESSION. Refresh tokens are per-issue, not
    per-user, so each device holds its own; a device that finds its access token
    gone gets a 401, spends its own refresh token, and carries on. The cost is
    one extra round trip per device per burst of requests, and the client's
    single-flight refresh keeps it to one.

    The alternative -- extending the existing token's `created` instead of
    replacing it -- is quieter and materially weaker: a stolen access token
    would then live as long as the real user keeps working, which is exactly
    what an expiry is for.

    ponytail: one access token per user, evicted on every issue. If staff need
    a phone and a shop tablet without the extra refresh, make the access token
    per-session -- a model of our own rather than DRF's, keyed on the refresh
    token that minted it.
    """
    Token.objects.filter(user=user).delete()
    return Token.objects.create(user=user)


def issue_session(user):
    """Return the payload every login answers with: access token plus refresh."""
    token = issue_access(user)
    _, raw_refresh = RefreshToken.issue(user, refresh_ttl())
    return {
        'token': token.key,
        'refresh': raw_refresh,
        'expires_in': access_ttl(),
    }


def rotate(raw_refresh):
    """Spend a refresh token for a new session, or return None.

    The presented token is revoked whether or not it was still live, and a
    token that was ALREADY revoked revokes the user's whole family. A revoked
    refresh token has only two ways of reaching this function: it was spent on
    an earlier rotation, or its holder signed out. Both mean the copy being
    presented now is one somebody kept -- so the safe reading is that a session
    has been captured, and the answer is to end every session that user has and
    make them sign in again.
    """
    record = RefreshToken.objects.filter(key_hash=hash_key(raw_refresh)).first()
    if record is None:
        return None
    if record.revoked_at is not None:
        revoke_all(record.user)
        return None
    if record.expires_at <= timezone.now():
        return None

    record.revoked_at = timezone.now()
    record.save(update_fields=['revoked_at'])
    return record.user, issue_session(record.user)


def revoke_all(user):
    """End every session this user holds: access token and all refresh tokens."""
    Token.objects.filter(user=user).delete()
    RefreshToken.objects.filter(user=user, revoked_at__isnull=True).update(
        revoked_at=timezone.now())
