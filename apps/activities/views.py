from rest_framework import viewsets

from core.permissions import SUPERVISOR_ROLES
from core.roles import OWNER, resolve_user_role
from .models import UniversalActivity
from .serializers import UniversalActivitySerializer

class UniversalActivityViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = UniversalActivity.objects.all()
    serializer_class = UniversalActivitySerializer

    def get_queryset(self):
        # The boutique-wide activity log, in prose, including order values in
        # the description and in new_value.total_amount. It had no scoping and
        # RolePermission grants every non-Owner staff member all SAFE_METHODS,
        # so any tailor could read the running commentary on every order in the
        # building. Whoever runs the floor needs this; whoever sews one garment
        # does not.
        role = resolve_user_role(self.request.user)
        if role != OWNER and role not in SUPERVISOR_ROLES:
            return UniversalActivity.objects.none()

        qs = super().get_queryset()
        module = self.request.query_params.get('module')
        entity_type = self.request.query_params.get('entity_type')
        entity_id = self.request.query_params.get('entity_id')

        if module:
            qs = qs.filter(module=module)
        if entity_type:
            qs = qs.filter(entity_type=entity_type)
        if entity_id:
            qs = qs.filter(entity_id=entity_id)

        return qs
