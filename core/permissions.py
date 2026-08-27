
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
