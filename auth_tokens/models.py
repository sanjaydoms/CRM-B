"""The refresh half of a session.

DRF's own Token is the access half and stays exactly as it is -- same model,
same `Authorization: Token <key>` header, same tenant-scoped table -- but it
now expires (see authentication.ExpiringTokenAuthentication). Something has to
let a phone that has been in a pocket all morning get a new one without asking
the tailor to type their password again, and that is this.

Why a whole app for one model, rather than putting it in crm_api: the platform
console signs in through the PUBLIC schema and crm_api is TENANT_APPS only, so
a model living there does not exist where the console needs it. This app is
registered in SHARED_APPS *and* TENANT_APPS, exactly as rest_framework.authtoken
already is, so the table exists in both places and one code path serves both
doors.

Only the hash is stored. A refresh token is a longer-lived credential than the
access token it mints, so the database should not be a place where reading one
row hands someone a live session -- the same reason Django never stores a
password.
"""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


def hash_key(raw):
    """The stored form of a refresh key.

    Plain SHA-256 with no salt or stretching, deliberately: the key is 256 bits
    from `secrets`, not a human-chosen password, so there is no dictionary to
    run and nothing for a work factor to buy. Unsalted also means the lookup is
    a single indexed equality test rather than a scan.
    """
    return hashlib.sha256(raw.encode()).hexdigest()


class RefreshToken(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='refresh_tokens',
        on_delete=models.CASCADE)
    key_hash = models.CharField(max_length=64, unique=True, db_index=True)
    created = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    # Set both when the holder signs out and when the token is spent on a
    # rotation. Presenting a revoked token is therefore either a replay of a
    # spent one or use of a signed-out session, and both are answered the same
    # way -- see services.rotate.
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['user', 'revoked_at'])]

    def __str__(self):
        return f'refresh for {self.user_id} until {self.expires_at:%Y-%m-%d}'

    @property
    def is_live(self):
        return self.revoked_at is None and self.expires_at > timezone.now()

    @classmethod
    def issue(cls, user, ttl_seconds):
        """Create one and return (instance, raw key). The raw key is not stored."""
        raw = secrets.token_urlsafe(32)
        token = cls.objects.create(
            user=user,
            key_hash=hash_key(raw),
            expires_at=timezone.now() + timedelta(seconds=ttl_seconds),
        )
        return token, raw
