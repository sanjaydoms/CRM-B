"""External platforms.

These are wired to the same interface as the internal sources but stay dormant
until credentials exist, so the studio ships and runs today without them. Each
reports itself as unavailable rather than raising, which lets the gallery show
"Pinterest -- not connected" instead of failing the whole search.

Note for whoever enables these: both platforms restrict storing and
redistributing result imagery. Import a result into the library only when the
boutique intends to use it as a reference, and keep ``source_url`` so
attribution back to the original survives.
"""

from django.conf import settings

from .base import DesignSourceProvider


class _CredentialGatedProvider(DesignSourceProvider):
    is_external = True
    setting_name = ''

    def credential(self):
        return getattr(settings, self.setting_name, '') or ''

    def available(self):
        return bool(self.credential())

    def search(self, queries, context, limit=20):
        if not self.available():
            return []
        raise NotImplementedError(
            f"{self.label} credentials are configured but no client is implemented yet."
        )


class PinterestProvider(_CredentialGatedProvider):
    key = 'pinterest'
    label = 'Pinterest'
    setting_name = 'DESIGN_STUDIO_PINTEREST_TOKEN'


class GoogleImagesProvider(_CredentialGatedProvider):
    key = 'google'
    label = 'Google Images'
    setting_name = 'DESIGN_STUDIO_GOOGLE_API_KEY'
