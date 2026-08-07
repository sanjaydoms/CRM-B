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
    SUPERVISOR_ORDER_ACTIONS = frozenset({'assign_stage'})

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

    from django.db.models import Q
    return queryset.filter(
        Q(orders__tailor=profile) | Q(orders__master=profile)
        | Q(orders__stages__assigned_to=profile)
    ).distinct()
