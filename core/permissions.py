
from rest_framework import permissions

from .modules import MODULES, module_for_path, role_allows
from .roles import DESIGNER, OWNER, resolve_user_role

SUPERVISOR_ROLES = frozenset({'Master'})


def _role_modules(request):
    """The owner's role -> module map for this boutique, read ONCE per request.

    Cached on the request because a single view can carry several permission
    classes and DRF instantiates and calls each one; without the cache a
    request pays one BoutiqueSettings query per class, per call, and
    has_object_permission paths pay it again. The cost is one indexed
    single-row query on the first governed check of a request and nothing
    after that.

    NOT cached beyond the request: the owner edits this map from a screen in
    the product, and a stale allow is an access-control bug rather than a slow
    page. Entitlement is not cached here at all -- see _module_permits, which
    no longer reads it, and tenants/middleware.py, which reads it fresh per
    request.

    Nothing here may raise. A permission class that throws is a 500 on every
    request it guards, so the three ways this lookup legitimately finds
    nothing -- no BoutiqueSettings row yet (a fresh boutique), no tenant schema
    at all (management commands, the public schema), a null or malformed
    column -- all resolve to {}: no explicit decisions recorded, so
    ROLE_DEFAULTS decides.
    """
    cached = getattr(request, '_role_modules', None)
    if cached is None:
        from crm_api.models import BoutiqueSettings
        try:
            # id=1 is the singleton row, the same one BoutiqueSettingsViewSet
            # get_or_creates and queue_order_ids reads.
            cached = BoutiqueSettings.objects.values_list(
                'role_modules', flat=True).filter(id=1).first()
        except Exception:
            cached = None
        if not isinstance(cached, dict):
            cached = {}
        request._role_modules = cached
    return cached


class ModuleAccess(permissions.BasePermission):
    """The module gate, and the base of every permission class in this codebase.

    Two layers decide whether a request may touch a module at all:

        effective(user) = ENTITLED(boutique) AND ALLOWED(role)

    Entitlement is the platform's (BoutiqueTenant.enabled_modules) and is
    enforced in TenantHeaderMiddleware. Distribution is the owner's
    (BoutiqueSettings.role_modules) and cannot be enforced there: the
    middleware runs before DRF authenticates, so request.user is AnonymousUser
    and the role is unknowable. Hence a permission class.

    WHY THIS IS THE BASE CLASS AND NOT A MIXIN OVER has_permission. About
    twenty-one views declare permission_classes explicitly, which replaces
    DEFAULT_PERMISSION_CLASSES outright -- adding the gate to the default alone
    would enforce nothing on payroll, staff, inventory or the design studio
    while looking like it did. The obvious fix, a mixin whose has_permission
    calls super(), does not work either: every class below defines its own
    has_permission, so Python finds the subclass method first and the mixin
    never runs. Verified, not assumed -- DesignLibraryPermission is the proof,
    it returns True outright for `create` without reaching super() at all.

    So has_permission is FINAL and lives here; the role rule each subclass used
    to put in has_permission now lives in has_role_permission, which this
    method calls after the gate. A subclass cannot skip the gate without
    deliberately re-defining has_permission, and core/test_module_enforcement.py
    fails if one ever does.

    It also works standalone: BasePermission's contract is "return True unless
    you object", so `permission_classes = [IsAuthenticated, ModuleAccess]` is
    the whole fix for a view that had no role class of its own.
    """

    def has_permission(self, request, view):
        key = module_for_path(request.path)
        # None means NOT GOVERNED, never "unknown, so deny": /api/auth/,
        # /api/dashboard/ and every prefix nobody has assigned a module to
        # resolve to None, and denying on it would switch off the product.
        if key is not None and not self._module_permits(request, key):
            return False
        return self.has_role_permission(request, view)

    def has_role_permission(self, request, view):
        """What this permission class actually decides. Override this one."""
        return True

    def _module_permits(self, request, key):
        """LAYER 2 ONLY. Entitlement is the middleware's and is not re-checked.

        It used to be re-checked here, off connection.tenant.enabled_modules,
        under a comment asserting that copy could not lag the console. It can,
        and that assertion is how this shipped. connection.tenant is the object
        tenants/middleware.py caches per process for 300 seconds, and
        clear_tenant_cache() clears the cache of the ONE worker that served the
        console write -- so for up to five minutes after the platform re-enabled
        a module, every other worker went on 403-ing the boutique owner with the
        entitlement wording, which sends them to support, where support looks at
        the console and sees the module enabled.

        Deleted rather than re-read from the row, because the re-check was
        redundant: nothing reaches DRF on a governed path without the
        middleware's own check, which IS fresh (_control_state() selects
        is_active/enabled_modules per request, not off the cached object).
        Traced rather than assumed, for every entry path:

          * TenantHeaderMiddleware.process_request runs on every request and
            refuses a governed path before any view sees it.
          * The only way past that check is `tenant is None`, and the same
            method then 400s every /api/ path except /api/auth/ and
            /api/superadmin/ -- both ALWAYS_ON, so module_for_path returns None
            for them and there is nothing to enforce.
          * /track/ is the one governed prefix outside /api/, and it is a plain
            Django view: crm_api/tracking_views.py resolves its own tenant from
            the signed token and reads is_enabled off the registry row itself.
            No permission class is involved.

        A second read here would buy nothing and cost a query per request.
        """
        # self.message is what DRF puts in the 403 body, and permission
        # instances are built per request (get_permissions() constructs them),
        # so writing to it here cannot leak one caller's refusal into another's.
        label = MODULES.get(key, (key,))[0]

        # Distribution. An unknown role gets the least-privileged
        # real role's defaults inside role_allows, never "everything".
        role = resolve_user_role(request.user)
        if role_allows(_role_modules(request), role, key):
            return True
        whose = f"the {role} role" if role else "your role"
        self.message = (f"The {label} module is not part of {whose}'s access "
                        f"at this boutique. Only the owner can change that, "
                        f"in Boutique Settings.")
        return False


class RolePermission(ModuleAccess):

    message = "Your role does not permit this."

    STAFF_ORDER_ACTIONS = frozenset({
        'transition_stage', 'submit_completion', 'submit_stage_review',
        'update_status',
        # Reversals reach the view for every staff member so the QC Staff can
        # fail a check; the precise role gates (Owner/Master for reopen,
        # +QC Staff for fail-qc) live in the services, where a refusal also
        # explains itself.
        'reopen_stage', 'fail_qc',
    })

    SUPERVISOR_ORDER_ACTIONS = frozenset({
        # The gathering checklist's writes: ticking a line and photographing
        # the material are the Owner's and the Master's, like the rest here.
        'gather', 'line_photo',
        'assign_stage', 'upload_garment_image', 'delete_garment_image',
        'publish_garment_images',
        'master_verification',
    })

    def has_role_permission(self, request, view):
        role = resolve_user_role(request.user)
        if role is None:
            return False
        if role == OWNER:
            return True
        if role == DESIGNER:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        action = getattr(view, 'action', None)
        if action in self.STAFF_ORDER_ACTIONS:
            return True
        return action in self.SUPERVISOR_ORDER_ACTIONS and role in SUPERVISOR_ROLES


class OwnNotifications(ModuleAccess):

    message = "Sign in to see your notifications."

    def has_role_permission(self, request, view):
        if resolve_user_role(request.user) is None:
            return False
        if getattr(view, 'action', None) == 'create':
            return False
        return True


class OwnerOnly(ModuleAccess):

    message = "Only the boutique owner can see this."

    def has_role_permission(self, request, view):
        return resolve_user_role(request.user) == OWNER


class StaffSelfOrOwner(ModuleAccess):
    """Employment records: the owner writes them, a staff member reads their own.

    Deliberately NOT RolePermission, which is the default for business
    endpoints. That class grants every non-Owner staff member every safe
    method -- correct for the order book, wrong here, because a GET on this
    viewset is the whole boutique's pay rates and deposit terms. A colleague's
    wage is the one thing on the floor that must not be readable by asking.

    This is one third of the rule. It decides what a caller may *do*; which
    rows they may do it to is StaffProfileViewSet.get_queryset; which fields of
    a visible row they may read is StaffProfileSerializer. All three are needed
    and none is sufficient: this class alone would let a tailor read every row,
    the queryset alone would let them PATCH their own hourly rate, and the two
    together still could not let a Master see the team WITHOUT seeing its pay.

    A supervisor reads, and only reads. Masters are given the roster by
    get_queryset because supervising a floor means knowing who is on it -- but
    the money on a colleague's row is removed by the serializer, and every
    write stays here, with the owner.

    THE FINANCIAL BOUNDARY, stated once so later phases inherit it: staff money
    is Owner-only. Payroll generation, approval, payment, deposit and advance
    movements, and any mutation of a rate are the owner's alone. A supervisor
    approving the wages of the people they supervise is the conflict this line
    exists to prevent. Later phases add endpoints, not exceptions -- anything
    that moves money uses OwnerOnly, not this class.
    """

    message = "Only the boutique owner can manage employment details."

    #: The writes a staff member performs ON THEMSELVES. Named actions rather
    #: than "POST is allowed", mirroring RolePermission.STAFF_ORDER_ACTIONS --
    #: which exists for the same reason: production staff need a few specific
    #: writes as part of doing the job, and listing them is what stops that need
    #: from opening every other write on the viewset.
    #:
    #: These are the METHOD names on the viewset (`check_in`), not the url_paths
    #: (`check-in`); DRF sets view.action from the method. Getting that backwards
    #: silently locks every staff member out of recording their own hours.
    #:
    #: Whose row is affected is not decided here -- the actions resolve the
    #: caller's own staff profile from the token and never read a staff id from
    #: the request body, so there is no id for anyone to substitute.
    #: `acknowledge` earns its place the same way: saying "I have seen my
    #: review" is a write, and without it here the acknowledgement step is
    #: unreachable by the only people entitled to perform it. The action itself
    #: still checks the review is theirs and is finalised.
    SELF_SERVICE_ACTIONS = frozenset({'check_in', 'check_out', 'acknowledge'})

    def has_role_permission(self, request, view):
        role = resolve_user_role(request.user)
        if role is None:
            return False
        if role == OWNER:
            return True
        if getattr(view, 'action', None) in self.SELF_SERVICE_ACTIONS:
            return True
        # Read-only for everyone else. A staff member raising their own pay is
        # the obvious thing to close, and it is closed here rather than by
        # trusting the interface not to offer the button.
        return request.method in permissions.SAFE_METHODS


class OwnerOrOwnFinancialRecord(ModuleAccess):
    """Financial records: the owner does everything, a staff member reads their own.

    For payslips and advances only. Everything that MOVES money -- generating,
    approving, paying, issuing, cancelling -- stays with OwnerOnly. This class
    exists because the Phase 6 access matrix lets a person read their own net
    pay and their own advance, and RolePermission would let them read
    everybody's.

    As with StaffSelfOrOwner, this is one third of the rule: it decides what a
    caller may DO. Which rows they may read is the viewset's get_queryset,
    which narrows a non-owner to rows whose staff is their own Tailor profile.
    A Master is a non-owner here -- supervising the floor grants nothing about
    what the floor is paid, and this class does not know or care about
    SUPERVISOR_ROLES.
    """

    message = "Only the boutique owner can manage payroll."

    def has_role_permission(self, request, view):
        role = resolve_user_role(request.user)
        if role is None:
            return False
        if role == OWNER:
            return True
        return request.method in permissions.SAFE_METHODS


#: A stage nobody has finished with. The inverse of workflow.SETTLED_STATUSES,
#: spelled here so this module does not import the engine just for a constant.
UNSETTLED_STATUSES = ('NOT_STARTED', 'IN_PROGRESS', 'PAUSED')


def stages_for_role(config, role):
    return [s['key'] for s in (config or [])
            if s.get('key') and role in (s.get('roles') or [])]


def queue_order_ids(queryset, user, role):
    from crm_api.models import BoutiqueSettings, OrderStage
    from domains.orders.workflow import prerequisites

    config = BoutiqueSettings.objects.values_list(
        'workflow_config', flat=True).filter(id=1).first() or []

    ids = set()
    for stage_key in stages_for_role(config, role):
        earlier = [s['key'] for s in prerequisites(config, stage_key)]
        ready = queryset.filter(
            stages__stage_key=stage_key, stages__status__in=UNSETTLED_STATUSES)
        if earlier:
            blocked = OrderStage.objects.filter(
                stage_key__in=earlier, status__in=UNSETTLED_STATUSES
            ).values('order_id')
            ready = ready.exclude(pk__in=blocked)
        ids.update(ready.values_list('id', flat=True))
    return ids


def visible_orders(queryset, user):
    role = resolve_user_role(user)
    if role == OWNER or role in SUPERVISOR_ROLES:
        return queryset

    profile = getattr(user, 'tailor_profile', None)
    if profile is None:
        return queryset.none()

    from django.db.models import Q
    match = (Q(tailor=profile) | Q(master=profile)
             | Q(stages__assigned_to=profile))
    queued = queue_order_ids(queryset, user, role)
    if queued:
        match |= Q(pk__in=queued)
    return queryset.filter(match).distinct()


def visible_customers(queryset, user):

    role = resolve_user_role(user)
    if role == OWNER or role in SUPERVISOR_ROLES:
        return queryset

    profile = getattr(user, 'tailor_profile', None)
    if profile is None:
        return queryset.none()

    from django.db.models import Q
    from crm_api.models import Customer, Order
    match = (Q(orders__tailor=profile) | Q(orders__master=profile)
             | Q(orders__stages__assigned_to=profile))
    queued = queue_order_ids(Order.objects.all(), user, role)
    if queued:
        match |= Q(orders__id__in=queued)
    return queryset.filter(pk__in=Customer.objects.filter(match).values('pk'))
