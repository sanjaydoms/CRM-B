
# The two role names that are not Tailor.ROLE_CHOICES values. Imported rather
# than respelled so there is one place a role string is written down; roles.py
# pulls in no Django at import time, which matters because middleware imports
# this module before the tenant schema is set.
from .roles import DESIGNER, OWNER

MODULES = {
    # Mounted at /api/order-drafts/ since the wizard learned to autosave, and
    # ungoverned until now: the platform console could switch off Orders'
    # neighbours and this prefix still answered for every boutique. Its own
    # key rather than a part of the (structural, ungateable) order book,
    # because a boutique that types orders in from paper once has no use for
    # half-finished ones and switching drafts off costs it nothing.
    'order_drafts': (
        'Order Drafts',
        ('/api/order-drafts/',),
        'Autosaved half-finished orders from the order wizard.',
    ),
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
    'finance': (
        'Cost & P&L',
        ('/api/finance/',),
        'Business costs the owner enters -- rent, utilities and the rest -- and '
        'the profit-and-loss report that nets them against revenue. Owner-only.',
    ),
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
    # Lives in SHARED_APPS -- one mailer for the platform -- but entitlement is
    # still per boutique: a boutique that has not bought outbound email must
    # not be able to send it, and this prefix answered for all of them until
    # it was registered here.
    'email': (
        'Email',
        ('/api/email/',),
        'Outbound transactional email: send, bulk send, queue and job status.',
    ),
}

#: The runs the boutique's own navigation is already grouped into
#: (frontend/src/App.jsx). Naming them here rather than in the sidebar means
#: the owner's access screen and the nav cannot drift into two different
#: answers about where Fabrics lives.
GROUPS = {
    'daily': 'Daily',
    'design': 'Design',
    'stock': 'Stock',
    'people': 'People',
    'business': 'Business',
    'operations': 'Operations',
    'platform': 'Platform',
}

#: A SEPARATE dict, deliberately not a fourth slot in the MODULES tuple.
#: Three call sites unpack that 3-tuple today -- superadmin/onboarding.py:61,
#: tenants/middleware.py and catalogue() below -- and a fourth element turns
#: every one of them into a ValueError at import time.
#:
#: `business` carries no module: invoices and reports are CLIENT_ONLY, computed
#: in the browser from data already fetched. The group stays because the nav
#: has it and a later server-side report belongs in it.
MODULE_GROUP = {
    'order_drafts': 'daily',
    'design_studio': 'design',
    'garment_catalog': 'design',
    'fabrics': 'stock',
    'inventory': 'stock',
    'inventory_catalog': 'stock',
    'tailors': 'people',
    'staff': 'people',
    'payroll': 'people',
    'finance': 'business',
    'scheduling': 'operations',
    'production_api': 'operations',
    'activities': 'operations',
    'notifications': 'operations',
    'order_tracking': 'operations',
    'email': 'platform',
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
    # A browser reporting that it crashed must never be refused by a module
    # switch or by maintenance mode. Those are precisely the states in which the
    # frontend is most likely to break, and a report lost then is the one worth
    # having.
    '/api/client-errors/',
    '/api/dashboard/',
    '/api/superadmin/',
    '/admin/',
    '/media/',
    '/demo-request/',
)

#: crm_api.models.Tailor.ROLE_CHOICES, verbatim and in order. Copied rather
#: than imported: this module is imported by TenantHeaderMiddleware, which runs
#: before the tenant schema is set, and importing a tenant model from here
#: drags the app registry into that path. core.checks asserts the two lists
#: still match, so a role added to the model without being added here fails
#: `manage.py check` instead of silently granting that role nothing.
PRODUCTION_ROLES = (
    'Master',
    'Tailor',
    'Maggam Master',
    'Karigar',
    'Packaging Staff',
    'QC Staff',
)

ALL_ROLES = (OWNER, DESIGNER) + PRODUCTION_ROLES

#: What a role sees when the owner has said nothing. Sparse storage means this
#: is the answer for almost every boutique almost all of the time, so it is a
#: product decision, not a placeholder.
#:
#: Owner is deliberately ABSENT. role_allows returns True for the owner on
#: anything the boutique is entitled to, because the owner is who distributes
#: access -- an owner who could switch off their own Inventory would have no
#: screen left to switch it back on, and no second owner to ask.
#:
#: The sets below were read off core/permissions.py rather than invented, so
#: that a role's default matches what the API would have let it do anyway.
#: Where the two disagree the permission class wins and this only ever narrows:
#:
#:  * Every role keeps `notifications`. The bell is on every screen; removing
#:    it does not hide a feature, it 403s the header of every page the role can
#:    still open. OwnNotifications already admits every known role.
#:  * `garment_catalog` is IsAuthenticated today (apps/catalog/views.py:33) and
#:    is what the order wizard reads its garment specs from. Everyone keeps it.
#:  * Production staff keep `staff`. The guidance says a tailor has no business
#:    in staff records, and for other people's records that is exactly right --
#:    but StaffSelfOrOwner.SELF_SERVICE_ACTIONS exists so a tailor can check
#:    themselves in and out, the roster is narrowed by get_queryset and pay is
#:    stripped by the serializer. "My Attendance" is one of the two entries in
#:    a tailor's whole navigation. Withholding the module here would delete the
#:    only way a tailor records their hours, so this is the documented conflict
#:    and the existing permission class wins.
#:  * `payroll` is withheld from production staff even though
#:    OwnerOrOwnFinancialRecord would let them read their own payslip: no
#:    screen reaches it, and StaffSelfOrOwner's financial boundary says staff
#:    money is the owner's. An owner who wants to publish payslips turns it on.
#:  * A Master supervises the floor, so they add the roster, the appointment
#:    book, production and the activity feed -- `activities` is already
#:    documented "Owner and Master only" in MODULES above -- plus
#:    `design_studio`, because DesignAssignmentPermission gives a Master full
#:    control of design assignments and "Design Work" is in their nav.
#:  * A Designer gets the Design Studio and the garment specs and nothing else.
#:    RolePermission already returns False for DESIGNER on every business
#:    endpoint; granting more here would be a second, contradictory answer.
#:  * The seven specialists are Tailor-shaped. They are the same job with a
#:    stage attached, and every place that has split them out so far
#:    (App.jsx PRODUCTION_ROLES, get_default_workflow) treats them alike.
#:  * Production staff keep `design_studio`. This looked like a module a
#:    tailor had no business in, and withholding it 403'd the approved design
#:    brief -- the picture and the tailor_instructions for the garment they are
#:    stitching right now. DesignStudioPermission already narrows what they get
#:    to approved boards, read-only, and their uploads into the approval queue;
#:    the module gate is a blunter instrument that was removing the brief along
#:    with everything else. A tailor who cannot see the design cannot make it.
_TAILOR = frozenset({'notifications', 'garment_catalog', 'staff',
                     'order_tracking', 'design_studio'})
_MASTER = _TAILOR | {'tailors', 'scheduling', 'production_api', 'activities'}
_DESIGNER = frozenset({'design_studio', 'garment_catalog', 'notifications'})

ROLE_DEFAULTS = {
    DESIGNER: _DESIGNER,
    'Master': frozenset(_MASTER),
    **{role: _TAILOR for role in PRODUCTION_ROLES if role != 'Master'},
}


def role_allows(role_modules, role, key):
    """Layer 2: of what the boutique has, does this role see it?"""
    if role == OWNER:
        return True
    # A dict per role, but the column arrives from JSON written by an API and
    # may be anything at all. A malformed value must read as "nothing explicit"
    # and fall through to the defaults -- never raise, because this runs inside
    # a permission class on every request.
    if isinstance(role_modules, dict):
        explicit = role_modules.get(role)
        if isinstance(explicit, dict) and key in explicit:
            return explicit[key] is not False
    # An unknown role -- None, or a value the model no longer has -- gets the
    # least-privileged real role, never everything. resolve_user_role returns
    # None for an account nothing claims (see core/roles.py: a deleted staff
    # member's live token), and that account must not inherit the floor.
    return key in ROLE_DEFAULTS.get(role, _TAILOR)


def effective_modules(enabled_modules, role_modules, role):
    """entitled(boutique) AND allowed(role). Layer 1 wins."""
    return sorted(
        key for key in MODULES
        if is_enabled(enabled_modules, key) and role_allows(role_modules, role, key)
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
        # 'group' is additive: superadmin/api_views.py and the console frontend
        # read 'key'/'label'/'prefixes'/'description'/'gateable' and keep
        # working untouched if they ignore it.
        'modules': [
            {'key': key, 'label': label, 'prefixes': list(prefixes), 'description': description,
             'gateable': True, 'group': MODULE_GROUP.get(key)}
            for key, (label, prefixes, description) in MODULES.items()
        ],
        'groups': dict(GROUPS),
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
