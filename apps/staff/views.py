from rest_framework import viewsets

from core.permissions import SUPERVISOR_ROLES, StaffSelfOrOwner
from core.roles import OWNER, resolve_user_role

from .models import StaffProfile
from .serializers import StaffProfileSerializer


class StaffProfileViewSet(viewsets.ModelViewSet):
    """Employment terms for the boutique's roster.

    Three layers guard this, and the pairing is the point:

      StaffSelfOrOwner   what a caller may DO -- only the owner writes.
      get_queryset       which rows EXIST for them.
      the serializer     which FIELDS of a visible row they may read.

    The third layer is what lets a Master supervise without being paid to
    supervise: they can see who is on the team and when they joined, and the
    money on someone else's row is removed on the way out. Scoping alone could
    not express that -- a row is either in the queryset or it is not.

    A tailor asking for a colleague's profile by id gets a 404 rather than a
    403, because DRF resolves the object through this queryset. The row is not
    hidden behind a refusal; it is simply not in their world, which is also the
    convention `visible_orders` already sets for the order book.
    """

    serializer_class = StaffProfileSerializer
    permission_classes = [StaffSelfOrOwner]

    def get_queryset(self):
        """Owner and supervisors see the roster; everyone else sees their own row.

        `SUPERVISOR_ROLES` is imported rather than restated. It is the same
        frozenset that decides who sees the whole order book in
        `visible_orders`, and a boutique that promotes a role to supervisor
        should not have to remember that Staff Management keeps its own list.

        `select_related('staff')` because the serializer reads `staff.name` and
        `staff.role` on every row -- without it a roster of twenty staff is
        twenty-one queries.
        """
        queryset = StaffProfile.objects.select_related('staff')
        role = resolve_user_role(self.request.user)
        if role == OWNER or role in SUPERVISOR_ROLES:
            return queryset

        # Everyone else: their own profile, reached through the Tailor row their
        # login is attached to. An account with no roster profile -- a
        # design-only designer, an orphaned login -- matches nothing, which is
        # the right answer rather than an error.
        profile = getattr(self.request.user, 'tailor_profile', None)
        if profile is None:
            return queryset.none()
        return queryset.filter(staff=profile)
