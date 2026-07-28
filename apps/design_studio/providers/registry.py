"""Which sources the studio searches, and in what order."""

from .external import GoogleImagesProvider, PinterestProvider
from .internal import CatalogueProvider, LibraryProvider, PastOrderProvider

_PROVIDERS = [
    CatalogueProvider(),
    LibraryProvider(),
    PastOrderProvider(),
    PinterestProvider(),
    GoogleImagesProvider(),
]


def all_providers():
    return list(_PROVIDERS)


def active_providers(keys=None):
    """Providers that can actually be searched, optionally filtered by key."""
    providers = [p for p in _PROVIDERS if p.available()]
    if keys:
        wanted = {str(k) for k in keys}
        providers = [p for p in providers if p.key in wanted]
    return providers


def source_status():
    """Per-source availability, so the gallery can label what it searched."""
    return [
        {
            'key': provider.key,
            'label': provider.label,
            'is_external': provider.is_external,
            'available': provider.available(),
        }
        for provider in _PROVIDERS
    ]
