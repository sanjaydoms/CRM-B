
MODULES = {
    'design_studio': (
        'Design Studio',
        ('/api/design-studio/', '/api/boutique-designs/'),
        'Design library, boards, collections, designers and AI discovery.',
    ),
    'inventory_catalog': (
        'Purchasing Catalogue',
        ('/api/inventory/catalog/',),
        'The fabric and trim catalogue inventory items are created from.',
    ),
    'inventory': (
        'Inventory',
        ('/api/inventory/',),
        'Stock, locations, suppliers, purchase orders and bills of materials.',
    ),
    'garment_catalog': (
        'Garment Templates',
        ('/api/catalog/',),
        'Garment specification templates used by the order wizard.',
    ),
    'scheduling': (
        'Appointments',
        ('/api/scheduling/',),
        'Customer appointments and the booking calendar.',
    ),
    'production_api': (
        'Production API',
        ('/api/production/',),
        'Production tasks and QC records. No screen calls this yet.',
    ),
    'activities': (
        'Activity Feed',
        ('/api/activities/',),
        'The cross-module activity stream. Owner and Master only.',
    ),
    'fabrics': (
        'Fabrics',
        ('/api/fabrics/',),
        "The boutique's own fabric library.",
    ),
    'tailors': (
        'Team',
        ('/api/tailors/',),
        'Tailors, masters and the specialist production roles.',
    ),
    'notifications': (
        'Notifications',
        ('/api/notifications/',),
        'The in-app notification bell. Switching this off breaks it on every screen.',
    ),
    'order_tracking': (
        'Public Order Tracking',
        ('/track/',),
        'The link a customer follows to watch their order. Public, no sign-in.',
    ),
}

STRUCTURAL = {
    'orders': (
        'Orders',
        'Carries payments, customer messaging, the production workflow and '
        'garment images on one prefix. Gating it would switch off all five.',
    ),
    'customers': (
        'Customers',
        'Carries measurements, design preferences and fabric selection. The '
        'order wizard cannot start without it.',
    ),
}

CLIENT_ONLY = {
    'invoices': 'Rendered in the browser from orders already fetched. No endpoint of its own.',
    'reports': 'Computed in the browser. The only server-side report is inventory reporting.',
    'try_on': 'Not implemented anywhere in this product.',
}

ALWAYS_ON = (
    '/api/auth/',
    '/api/boutique-settings/',
    '/api/dashboard/',
    '/api/superadmin/',
    '/admin/',
    '/media/',
    '/demo-request/',
)

_ORDERED = sorted(
    ((prefix, key) for key, (_, prefixes, _d) in MODULES.items() for prefix in prefixes),
    key=lambda pair: len(pair[0]),
    reverse=True,
)


def _normalise(path):
    head, sep, last = path.rstrip('/').rpartition('/')
    if sep and '.' in last:
        last = last.split('.', 1)[0]
        path = f'{head}/{last}'
    return path if path.endswith('/') else path + '/'


def module_for_path(path):
    candidates = (path, _normalise(path))
    for always in ALWAYS_ON:
        if any(c.startswith(always) for c in candidates):
            return None
    for prefix, key in _ORDERED:
        if any(c.startswith(prefix) for c in candidates):
            return key
    return None


def default_enabled():
    return {key: True for key in MODULES}


def is_enabled(enabled_modules, key):
    if not isinstance(enabled_modules, dict) or not enabled_modules:
        return True
    return enabled_modules.get(key, True) is not False


def catalogue():
    return {
        'modules': [
            {'key': key, 'label': label, 'prefixes': list(prefixes), 'description': description,
             'gateable': True}
            for key, (label, prefixes, description) in MODULES.items()
        ],
        'structural': [
            {'key': key, 'label': label, 'reason': reason, 'gateable': False}
            for key, (label, reason) in STRUCTURAL.items()
        ],
        'client_only': [
            {'key': key, 'reason': reason, 'gateable': False}
            for key, reason in CLIENT_ONLY.items()
        ],
        'always_on': list(ALWAYS_ON),
    }
