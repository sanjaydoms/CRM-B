"""What a "module" is, and which URLs constitute it.

This is the single definition of the product's feature surface. It lives in
`core` rather than in `superadmin` or `tenants` because both of those import it
and importing it the other way round would be a cycle: `tenants.middleware`
enforces the gate, `superadmin.views` presents it, and `core` imports neither.

Two rules were learned the hard way from reading the URLconf and are encoded
here rather than left to whoever edits this next:

**Match the longest prefix first.** `/api/inventory/catalog/` is a child of
`/api/inventory/`. Sorted the other way, switching off purchasing would silently
switch off the fabric catalogue too.

**Never gate the bare `/api/`.** `crm_api` is mounted there (boutique_crm/urls.py)
*alongside login*, so a rule keyed on `/api/` locks every boutique out of its own
account with no way back in. Every prefix below names a router, not the mount.

ALWAYS_ON exists for the same reason: authentication, the boutique's own
settings, the dashboard the app lands on, the public tracking page and the
platform console can never be switched off, whatever is stored against a tenant.
A console that can lock itself out is a console that will.

On what is deliberately NOT here
--------------------------------
The Super Admin specification asks for switches over Invoices, Reports and
Try-On. None of them has a server surface:

  * Invoices and Reports/Analytics are arithmetic the browser does over the
    orders it already fetched. A switch would hide a menu item and `curl` would
    walk straight past it.
  * Try-On does not exist in any form -- "TryOn2Buy" is the company name in the
    README and nothing else.

A switch that controls nothing is worse than no switch, because it reads as a
security control and is not one. They are listed in CLIENT_ONLY below so the
console can say plainly why they are absent, rather than leaving someone to
wonder whether the list is just incomplete.
"""

#: key -> (label, url prefixes, human description)
#:
#: Every prefix is a router mount taken from the project URLconf, verified
#: against each app's urls.py.
MODULES = {
    'design_studio': (
        'Design Studio',
        ('/api/design-studio/', '/api/boutique-designs/'),
        'Design library, boards, collections, designers and AI discovery.',
    ),
    # Must be listed -- and matched -- before `inventory`, whose prefix contains
    # it. _match() sorts by length to guarantee that regardless of order here.
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
    # Distinct from `tailors`, which is the roster. This is the employment
    # layer over it: terms, attendance, payroll and performance. Switching it
    # off leaves the roster and the whole production workflow untouched, which
    # is why it can be its own switch at all.
    'staff': (
        'Staff Management',
        ('/api/staff/',),
        'Employment terms, attendance, payroll and staff performance.',
    ),
    # Its own switch rather than a part of `staff`: a boutique may well want
    # attendance and employment records without running its wages through the
    # product, and payroll is the one surface where switching it off has to
    # switch off everything -- generation, approval and every figure.
    'payroll': (
        'Payroll',
        ('/api/payroll/',),
        'Weekly staff payroll: hours, rates and approved gross earnings.',
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

#: Modules that carry more than one product concern on a single URL prefix, and
#: so cannot be switched off without taking the others with them. Listed rather
#: than quietly omitted, because "why is Orders not in the list" is the first
#: question anyone reading the console will ask.
#:
#: /api/orders/ alone carries order CRUD, payment reconciliation, the customer
#: messaging queue, the whole production workflow and garment photography.
#: /api/customers/ carries measurements, design preferences and fabric
#: selection, and steps 1-2 of the order wizard stop working without it.
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

#: Surfaces the specification names that exist only in the browser. A switch
#: here would hide a menu and stop nothing.
CLIENT_ONLY = {
    'invoices': 'Rendered in the browser from orders already fetched. No endpoint of its own.',
    'reports': 'Computed in the browser. The only server-side report is inventory reporting.',
    'try_on': 'Not implemented anywhere in this product.',
}

#: Never gateable, whatever is stored against a tenant.
#:
#: `/api/auth/` is first and is the one that matters: it shares the `/api/`
#: mount with the business routers, and locking it would end the boutique's
#: access to its own account permanently.
ALWAYS_ON = (
    '/api/auth/',
    '/api/boutique-settings/',
    '/api/dashboard/',
    '/api/superadmin/',
    '/admin/',
    '/media/',
    '/demo-request/',
)

#: Longest first, so a child prefix is tested before its parent.
_ORDERED = sorted(
    ((prefix, key) for key, (_, prefixes, _d) in MODULES.items() for prefix in prefixes),
    key=lambda pair: len(pair[0]),
    reverse=True,
)


def _normalise(path):
    """The canonical form of a request path, for prefix matching.

    Two things a raw `startswith` misses, both of which were live bypasses:

    **DRF format suffixes.** `crm_api/urls.py` uses `DefaultRouter`, which
    publishes every list route a second time as `fabrics\\.(?P<format>[a-z0-9]+)`.
    So `/api/fabrics.json` serves the same data as `/api/fabrics/` and does not
    start with `/api/fabrics/`. A switched-off module stayed fully readable and
    writable through one extra character.

    **The missing trailing slash.** `APPEND_SLASH` redirects `/api/fabrics` to
    `/api/fabrics/`, but `CommonMiddleware` is *after* this one, so the gate saw
    the slashless form first. The redirect makes that harmless for a browser,
    which retries and is then gated -- but relying on a later middleware to
    close a hole in this one is not a property worth depending on.

    Both are handled by canonicalising rather than by adding patterns, so a
    router added later inherits the fix.
    """
    head, sep, last = path.rstrip('/').rpartition('/')
    if sep and '.' in last:
        last = last.split('.', 1)[0]
        path = f'{head}/{last}'
    return path if path.endswith('/') else path + '/'


def module_for_path(path):
    """Which module owns `path`, or None if nothing does.

    None means "not governed" -- an always-on route, or one no module claims.
    The caller must treat None as allow, never as deny: a route that no rule
    covers has not been switched off by anybody.

    Matched against the raw path *and* its canonical form, and a hit on either
    governs. Fail-closed is the right direction for a gate: the cost of an
    over-broad match is a module that is off being off, and the cost of a missed
    one is a module that is off being served.
    """
    candidates = (path, _normalise(path))
    for always in ALWAYS_ON:
        if any(c.startswith(always) for c in candidates):
            return None
    for prefix, key in _ORDERED:
        if any(c.startswith(prefix) for c in candidates):
            return key
    return None


def default_enabled():
    """Every module on. What a boutique gets when nobody has said otherwise.

    A new module must be ON by default, or adding one to this file would
    silently switch it off for every existing boutique at deploy time.
    """
    return {key: True for key in MODULES}


def is_enabled(enabled_modules, key):
    """Whether `key` is on, given a tenant's stored map.

    Absent means enabled, for the reason in default_enabled(): a tenant row
    written before a module existed has no opinion about it, and "no opinion"
    must not read as "off".

    A non-dict value also reads as enabled. The column is a JSONField rendered
    as a free textarea in the Django admin, so `["fabrics"]` or `"off"` can be
    saved by hand -- and a list is truthy, so a bare `.get()` would raise
    AttributeError *inside the middleware*, turning one bad edit into a 500 on
    every governed endpoint for that boutique with no way to reach the screen
    that would fix it. Treating a malformed value as "no opinion" degrades to
    the safe direction: the boutique keeps working, and the switches simply have
    no effect until someone corrects the column.
    """
    if not isinstance(enabled_modules, dict) or not enabled_modules:
        return True
    return enabled_modules.get(key, True) is not False


def catalogue():
    """The whole feature surface, for the console to render.

    Includes the structural and client-only entries so the console can explain
    what is missing and why, rather than presenting a list with holes in it.
    """
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
