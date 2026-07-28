"""Role rules for the studio.

Spec'd access: the Owner runs the studio end to end; a Master sees the selected
design and adds production notes; a Tailor sees the approved design and its
instructions and nothing else. Roles come from ``core.roles`` so the studio
cannot drift from the rest of the app the way the workflow engine once did.
"""

from rest_framework import permissions

from core.roles import OWNER, resolve_user_role

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
