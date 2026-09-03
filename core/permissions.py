
from rest_framework import permissions

from .roles import DESIGNER, OWNER, resolve_user_role

SUPERVISOR_ROLES = frozenset({'Master'})


class RolePermission(permissions.BasePermission):

    message = "Your role does not permit this."

    STAFF_ORDER_ACTIONS = frozenset({
        'transition_stage', 'submit_completion', 'submit_stage_review',
        'update_status',
    })

    SUPERVISOR_ORDER_ACTIONS = frozenset({
        'assign_stage', 'upload_garment_image', 'delete_garment_image',
        'publish_garment_images',
        'master_verification',
    })

    def has_permission(self, request, view):
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


class OwnNotifications(permissions.BasePermission):

    message = "Sign in to see your notifications."

    def has_permission(self, request, view):
        if resolve_user_role(request.user) is None:
            return False
        if getattr(view, 'action', None) == 'create':
            return False
        return True


class OwnerOnly(permissions.BasePermission):

    message = "Only the boutique owner can see this."

    def has_permission(self, request, view):
        return resolve_user_role(request.user) == OWNER


class StaffSelfOrOwner(permissions.BasePermission):
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

    def has_permission(self, request, view):
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


class OwnerOrOwnFinancialRecord(permissions.BasePermission):
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

    def has_permission(self, request, view):
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
