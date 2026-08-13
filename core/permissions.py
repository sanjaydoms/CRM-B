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


def visible_orders(queryset, user):
    """Narrow `queryset` to the orders this user is allowed to see.

    Owners and Masters see the floor. Everyone else sees the orders they are on
    -- as the assigned tailor, as the master, or through a stage assigned to
    them -- because a tailor reading the whole order book is how a customer
    list walks out of the building.
    """
    role = resolve_user_role(user)
    if role == OWNER or role in SUPERVISOR_ROLES:
        return queryset

    profile = getattr(user, 'tailor_profile', None)
    if profile is None:
        return queryset.none()

    from django.db.models import Q
    return queryset.filter(
        Q(tailor=profile) | Q(master=profile) | Q(stages__assigned_to=profile)
    ).distinct()


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
    from crm_api.models import Customer
    return queryset.filter(pk__in=Customer.objects.filter(
        Q(orders__tailor=profile) | Q(orders__master=profile)
        | Q(orders__stages__assigned_to=profile)
    ).values('pk'))
