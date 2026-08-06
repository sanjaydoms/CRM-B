"""Role rules for the studio.

Spec'd access: the Owner runs the studio end to end; a Master sees the selected
design and adds production notes; a Tailor sees the approved design and its
instructions and nothing else. Roles come from ``core.roles`` so the studio
cannot drift from the rest of the app the way the workflow engine once did.
"""

from rest_framework import permissions

from core.roles import DESIGNER, OWNER, resolve_user_role

MASTER = 'Master'
TAILOR = 'Tailor'


class DesignStudioPermission(permissions.BasePermission):
    """Owner: full access. Master: read + production notes. Tailor: read only."""

    message = "Your role does not permit this action in the Design Studio."

    def has_permission(self, request, view):
        role = resolve_user_role(request.user)
        if role is None:
            return False
        if role == OWNER:
            return True
        if request.method in permissions.SAFE_METHODS:
            return True
        # The one write a non-owner gets is a Master leaving production notes.
        return role == MASTER and getattr(view, 'action', None) == 'production_notes'


class DesignLibraryPermission(DesignStudioPermission):
    """DesignAssetViewSet's rule: everything DesignStudioPermission allows, plus
    upload, plus a designer editing their own work.

    Any signed-in staff member may add a design -- someone at the counter
    photographing a customer's reference is exactly the case the approval queue
    exists for, and gating the upload itself on Owner would make that queue
    permanently empty until designers have their own accounts.

    Editing and deleting someone else's upload stay Owner-only. A designer may
    edit or delete their own: step 7 is the point at which "there is no account
    to check ownership against" stops being true, so the matrix's "Designer:
    edit only own uploads" can finally be enforced rather than just written
    down.
    """

    OWN_UPLOAD_ACTIONS = {'update', 'partial_update', 'destroy'}

    def has_permission(self, request, view):
        action = getattr(view, 'action', None)
        if action == 'create':
            return resolve_user_role(request.user) is not None
        if action in self.OWN_UPLOAD_ACTIONS and resolve_user_role(request.user) == DESIGNER:
            # Whether this is *their* upload needs the object, which is not
            # loaded yet at this point in the request -- has_object_permission
            # below makes that call once it is. A Designer who turns out not to
            # own the design is refused there, not here.
            return True
        return super().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        role = resolve_user_role(request.user)
        if role == OWNER:
            return True
        if role == DESIGNER and getattr(view, 'action', None) in self.OWN_UPLOAD_ACTIONS:
            designer = getattr(request.user, 'designer_profile', None)
            return designer is not None and obj.designer_ref_id == designer.id
        # Nothing else reaches here with a write action -- has_permission
        # already turned away every other case. Reads fall back to the parent
        # rule, which is SAFE_METHODS-open to any authenticated role.
        return super().has_permission(request, view)


class OwnerOnly(permissions.BasePermission):
    message = "Only the boutique owner can use design discovery."

    def has_permission(self, request, view):
        return resolve_user_role(request.user) == OWNER


def visible_boards(queryset, user):
    """Narrow a board queryset to what the caller's role may see.

    A Tailor is shown approved boards only -- a shortlist still under
    discussion is not a production instruction and showing it would invite
    someone to start stitching the wrong design.
    """
    role = resolve_user_role(user)
    if role == OWNER:
        return queryset
    if role == MASTER:
        return queryset.exclude(status=queryset.model.STATUS_DRAFT)
    if role == TAILOR:
        return queryset.filter(status=queryset.model.STATUS_APPROVED)
    return queryset.none()
