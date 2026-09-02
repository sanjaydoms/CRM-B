
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
