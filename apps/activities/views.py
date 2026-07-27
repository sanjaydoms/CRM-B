from rest_framework import viewsets
from .models import UniversalActivity
from .serializers import UniversalActivitySerializer

class UniversalActivityViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = UniversalActivity.objects.all()
    serializer_class = UniversalActivitySerializer

    def get_queryset(self):
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
