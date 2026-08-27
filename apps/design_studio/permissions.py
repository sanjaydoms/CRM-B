
from rest_framework import permissions

from core.permissions import OwnerOnly as CoreOwnerOnly
from core.roles import DESIGNER, OWNER, resolve_user_role

MASTER = 'Master'
TAILOR = 'Tailor'


class DesignStudioPermission(permissions.BasePermission):

    message = "Your role does not permit this action in the Design Studio."

    def has_permission(self, request, view):
        role = resolve_user_role(request.user)
        if role is None:
            return False
        if role == OWNER:
            return True
        if request.method in permissions.SAFE_METHODS:
            return True
        return role == MASTER and getattr(view, 'action', None) == 'production_notes'


class DesignLibraryPermission(DesignStudioPermission):

    OWN_UPLOAD_ACTIONS = {'update', 'partial_update', 'destroy'}

    def has_permission(self, request, view):
        action = getattr(view, 'action', None)
        if action == 'create':
            return resolve_user_role(request.user) is not None
        if action in self.OWN_UPLOAD_ACTIONS and resolve_user_role(request.user) == DESIGNER:
            return True
        return super().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        role = resolve_user_role(request.user)
        if role == OWNER:
            return True
        if role == DESIGNER and getattr(view, 'action', None) in self.OWN_UPLOAD_ACTIONS:
            return obj.created_by_id == request.user.id
        return super().has_permission(request, view)


class OwnerOnly(CoreOwnerOnly):

    message = "Only the boutique owner can use design discovery."


def visible_boards(queryset, user):
    role = resolve_user_role(user)
    if role == OWNER:
        return queryset
    if role == MASTER:
        return queryset.exclude(status=queryset.model.STATUS_DRAFT)
    if getattr(user, 'tailor_profile', None) is not None:
        return queryset.filter(status=queryset.model.STATUS_APPROVED)
    return queryset.none()


class DesignAssignmentPermission(permissions.BasePermission):

    message = "Your role does not permit this action on design assignments."

    SUPERVISOR_ACTIONS = {'create', 'update', 'partial_update', 'destroy', 'review'}
    DESIGNER_ACTIONS = {'list', 'retrieve', 'submit'}

    def has_permission(self, request, view):
        role = resolve_user_role(request.user)
        if role is None:
            return False
        if role in (OWNER, MASTER):
            return True
        if role == DESIGNER:
            return getattr(view, 'action', None) in self.DESIGNER_ACTIONS
        return False


def visible_assignments(queryset, user):
    role = resolve_user_role(user)
    if role in (OWNER, MASTER):
        return queryset
    if role == DESIGNER:
        profile = getattr(user, 'designer_profile', None)
        if profile is None:
            return queryset.none()
        return queryset.filter(designer_id=profile.id)
    return queryset.none()
