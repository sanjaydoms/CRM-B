from rest_framework import viewsets

from core.permissions import StaffSelfOrOwner
from core.roles import OWNER, resolve_user_role

from .models import StaffProfile
from .serializers import StaffProfileSerializer


class StaffProfileViewSet(viewsets.ModelViewSet):
    """Employment terms for the boutique's roster.

    Two layers guard this, and the pairing is the point (see StaffSelfOrOwner):
    the permission class says what a caller may do, `get_queryset` says which
    rows exist as far as they are concerned. A tailor asking for a colleague's
    profile by id gets a 404 rather than a 403, because DRF resolves the object
    through this queryset -- the row is not hidden behind a refusal, it is
    simply not in their world.
    """

    serializer_class = StaffProfileSerializer
    permission_classes = [StaffSelfOrOwner]

    def get_queryset(self):
        """The owner sees the roster's terms; everyone else sees their own row.

        `select_related('staff')` because the serializer reads `staff.name` and
        `staff.role` on every row -- without it a roster of twenty staff is
        twenty-one queries.
        """
        queryset = StaffProfile.objects.select_related('staff')
        if resolve_user_role(self.request.user) == OWNER:
            return queryset

        # Everyone else: their own profile, reached through the Tailor row their
        # login is attached to. An account with no roster profile -- a
        # design-only designer, an orphaned login -- matches nothing, which is
        # the right answer rather than an error.
        profile = getattr(self.request.user, 'tailor_profile', None)
        if profile is None:
            return queryset.none()
        return queryset.filter(staff=profile)
