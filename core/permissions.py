"""Who may do what, enforced at the API rather than in the interface.

Until now a staff member's role only shaped which menu items the frontend drew.
The API itself let any signed-in account read the whole boutique: every
customer's contact details, every order's money, the staff list, stock
valuation and cost-per-order. A tailor with a browser's dev tools -- or anyone
who ended up with a tailor's token -- had the lot.

Two rules, applied together:

  RolePermission    denies writes that are not the caller's to make.
  visible_orders    scopes what a tailor can read to their own work.

Roles come from core.roles so this cannot drift from the workflow engine, which
is the mistake that module's docstring already records.
"""

from rest_framework import permissions

from .roles import DESIGNER, OWNER, resolve_user_role

#: Everyone who works on garments. Masters supervise, so they see the floor;
#: the rest see what they were given.
SUPERVISOR_ROLES = frozenset({'Master'})


class RolePermission(permissions.BasePermission):
    """The default for every business endpoint.

    Owner does everything. Production staff read, and write only through the
    order actions that are their job. A designer gets nothing here at all --
    the Design Studio has its own permission classes, and those views set them
    explicitly, so reaching this class means the designer is somewhere that is
    not theirs.
    """

    message = "Your role does not permit this."

    #: Order actions production staff perform as part of the work itself.
    #: These are the *method* names on the viewset, not the url_paths -- DRF
    #: sets view.action from the method, so `transition_stage` here and
    #: `transition` in the URL. Getting that wrong locks a tailor out of
    #: advancing their own stage, which is how this list was first written.
    STAFF_ORDER_ACTIONS = frozenset({
        'transition_stage', 'submit_completion', 'submit_stage_review',
        'update_status',
    })

    #: Handing work to someone else is a supervisor's call, not a tailor's.
    #: The finished-garment photographs belong here too: the specification has
    #: the owner or the master taking and publishing them, and publishing is
    #: what tells the customer their outfit is ready.
    SUPERVISOR_ORDER_ACTIONS = frozenset({
        'assign_stage', 'upload_garment_image', 'delete_garment_image',
        'publish_garment_images',
        # The Master's production checklist. It has its own narrow action
        # precisely so it can live here: the checklist used to be saved with a
        # plain PATCH of the order, which DRF calls 'partial_update', and that
        # action also carries payment_status and amount_paid. Admitting it
        # wholesale would have opened the money fields to a supervisor to make
        # a row of tick boxes work.
        'master_verification',
    })

    def has_permission(self, request, view):
        role = resolve_user_role(request.user)
        if role is None:
            return False
        if role == OWNER:
            return True
        if role == DESIGNER:
            # A design-only account has no business in customers, orders,
            # inventory or settings. Its own module grants its own access.
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        action = getattr(view, 'action', None)
        if action in self.STAFF_ORDER_ACTIONS:
            return True
        return action in self.SUPERVISOR_ORDER_ACTIONS and role in SUPERVISOR_ROLES


class OwnNotifications(permissions.BasePermission):
    """Anyone signed in may read and clear their OWN notification feed.

    NotificationViewSet used the default RolePermission, which allows a
    non-Owner every safe method but only the named order actions as writes --
    and mark-all-read is a POST that is on neither list. So every staff member
    got a 403 the moment they opened the notification drawer, and because the
    frontend surfaced that as a thrown error inside the click handler, the
    whole application dropped to its runtime-error screen. The bell is on every
    screen, so a tailor lost the app on their first click.

    Safe without a role check for READS and updates: get_queryset derives the
    audience from the signed-in user, so both are already confined to the
    caller's own rows.

    Creation is the exception, and the sentence above used to cover it by
    mistake -- `create` never calls get_queryset, and NotificationSerializer is
    fields='__all__' over a writable recipient_role and recipient_email. So any
    signed-in staff member could POST a notification addressed to the OWNER,
    with any title and body they liked, and it appeared in the owner's bell
    indistinguishable from one the system had raised. Notifications are how this
    product tells the owner an order needs attention or a payment has landed.

    Nothing legitimately creates one over HTTP: every real notification is
    written server-side by domains/orders/notifications.py.
    """

    message = "Sign in to see your notifications."

    def has_permission(self, request, view):
        if resolve_user_role(request.user) is None:
            return False
        # Refused for everyone, including the Owner -- there is no caller for
        # it. `destroy` needs no clause here because it resolves its object
        # through the scoped get_queryset, and `mark_all_read` is a custom
        # action with its own name.
        #
        # Deliberately NOT http_method_names = [...] without 'post':
        # APIView.dispatch tests that list before it maps the action, so
        # dropping POST would 405 mark-all-read and take the notification bell
        # down for every non-Owner -- which is the outage this class was
        # written to fix in the first place.
        if getattr(view, 'action', None) == 'create':
            return False
        return True


class OwnerOnly(permissions.BasePermission):
    """For the things only the person who owns the business should see.

    Stock valuation, cost per order and supplier performance are the boutique's
    commercial position. A tailor needs none of it to sew.
    """

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

    def has_permission(self, request, view):
        role = resolve_user_role(request.user)
        if role is None:
            return False
        if role == OWNER:
            return True
        # Read-only for everyone else. A staff member raising their own pay is
        # the obvious thing to close, and it is closed here rather than by
        # trusting the interface not to offer the button.
        return request.method in permissions.SAFE_METHODS


#: A stage nobody has finished with. The inverse of workflow.SETTLED_STATUSES,
#: spelled here so this module does not import the engine just for a constant.
UNSETTLED_STATUSES = ('NOT_STARTED', 'IN_PROGRESS', 'PAUSED')


def stages_for_role(config, role):
    """The stage keys this role is declared able to perform.

    Reads workflow_config's own `roles` list -- the SAME declaration
    workflow.check_transition enforces on the way in. That shared source is the
    point: a role is shown exactly the work it is permitted to do, so
    "what I can see" and "what I may touch" cannot drift apart. Two lists would.
    """
    return [s['key'] for s in (config or [])
            if s.get('key') and role in (s.get('roles') or [])]


def queue_order_ids(queryset, user, role):
    """Orders sitting on this role's desk right now.

    Work "has reached" a role when a stage they may perform is still open AND
    everything required before it is settled -- which is precisely the condition
    workflow.check_transition would accept, asked ahead of time instead of at
    the moment of the click.

    This is what makes a specialist role discoverable at all. A QC Master is
    never order.tailor (that is the stitcher) nor order.master (that is the
    supervisor), so before this they saw an order only if a human remembered to
    run assign-stage against them. Orders reached quality check and sat there
    invisible, and the inspection got completed by whoever could see it.

    Readiness is what keeps it honest in the other direction: without it, every
    order ever taken would carry a NOT_STARTED quality-check stage and the whole
    order book would land in the QC Master's lap on day one. They see the ones
    actually waiting for them, and nothing else.

    ponytail: one small query per stage the role owns. Specialists own one stage
    each and Masters short-circuit above, so this is 1-2 queries in practice.
    Fold into a single window function if a boutique ever declares a role onto
    many stages.
    """
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
            # An explicit subquery, NOT exclude(stages__a=..., stages__b=...).
            # Across a multi-valued relation Django compiles that pair into two
            # INDEPENDENT EXISTS clauses -- "has some earlier stage" AND "has
            # some unsettled stage" -- which are satisfied by different rows.
            # Every order sitting at quality check still has unsettled stages
            # after it (trial, delivery), so that form excluded every order in
            # the boutique and the queue came back empty. Both conditions have
            # to describe ONE stage row, which is what this says.
            blocked = OrderStage.objects.filter(
                stage_key__in=earlier, status__in=UNSETTLED_STATUSES
            ).values('order_id')
            ready = ready.exclude(pk__in=blocked)
        ids.update(ready.values_list('id', flat=True))
    return ids


def visible_orders(queryset, user):
    """Narrow `queryset` to the orders this user is allowed to see.

    Owners and Masters see the floor. Everyone else sees the orders they are on
    -- as the assigned tailor, as the master, through a stage assigned to them,
    or because the order has reached a stage their role performs -- because a
    tailor reading the whole order book is how a customer list walks out of the
    building.

    That last clause is the work queue. The three before it are all personal
    attachment, which a specialist never has until somebody grants it by hand.
    """
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
    """The customers behind the orders this user can see."""
    role = resolve_user_role(user)
    if role == OWNER or role in SUPERVISOR_ROLES:
        return queryset

    profile = getattr(user, 'tailor_profile', None)
    if profile is None:
        return queryset.none()

    # Matched through a subquery rather than by joining, because the join is
    # what forced distinct=True onto the aggregates in
    # CustomerRepository.summary_queryset -- and Sum(DISTINCT col) de-duplicates
    # by VALUE, not by row, so two orders at the same price counted once.
    #
    # Filtering on `orders__stages__assigned_to` multiplies each customer row by
    # every stage of every one of their orders (fifteen stages per order), so the
    # annotations further up the queryset saw each order fifteen times. Doing the
    # matching inside a subquery leaves the outer queryset with no multi-valued
    # join at all: the aggregates then see each order exactly once, distinct is
    # unnecessary, and the trailing .distinct() that was papering over the row
    # list goes too.
    from django.db.models import Q
    from crm_api.models import Customer, Order
    match = (Q(orders__tailor=profile) | Q(orders__master=profile)
             | Q(orders__stages__assigned_to=profile))
    # Kept deliberately in step with visible_orders: a role that can see an
    # order must be able to resolve whose it is, or the queue renders rows with
    # no customer on them.
    queued = queue_order_ids(Order.objects.all(), user, role)
    if queued:
        match |= Q(orders__id__in=queued)
    return queryset.filter(pk__in=Customer.objects.filter(match).values('pk'))
