

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

    providers = [p for p in _PROVIDERS if p.available()]
    if keys:
        wanted = {str(k) for k in keys}
        providers = [p for p in providers if p.key in wanted]
    return providers


def source_status():

    return [
        {
            'key': provider.key,
            'label': provider.label,
            'is_external': provider.is_external,
            'available': provider.available(),
        }
        for provider in _PROVIDERS
    ]
