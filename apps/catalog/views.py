from django.db.models import Prefetch
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.permissions import visible_orders
from core.templates import SpecValidationError, validate_spec
from crm_api.models import Order

from .models import (
    GarmentJob, GarmentTemplate, JobMaterial, TemplateField, TemplateSection,
)
from .serializers import (
    GarmentJobSerializer, GarmentTemplateSerializer, GarmentTemplateSummarySerializer,
    JobMaterialSerializer,
)


def _full_template_queryset():
    return GarmentTemplate.objects.prefetch_related(
        Prefetch(
            'sections',
            queryset=TemplateSection.objects.prefetch_related(
                Prefetch('fields', queryset=TemplateField.objects.prefetch_related('options'))
            ),
        )
    )


class GarmentTemplateViewSet(viewsets.ReadOnlyModelViewSet):

    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'key'
    serializer_class = GarmentTemplateSerializer

    def get_queryset(self):
        queryset = _full_template_queryset().filter(is_active=True)
        label = self.request.headers.get('X-Template-Variant')
        if label:
            forked = set(
                GarmentTemplate.objects.filter(tenant=label, is_active=True)
                .values_list('key', flat=True)
            )
            return queryset.filter(tenant__in=[label, None]).exclude(
                tenant__isnull=True, key__in=forked
            )
        return queryset.filter(tenant__isnull=True)

    def get_serializer_class(self):
        if self.action == 'list':
            return GarmentTemplateSummarySerializer
        return GarmentTemplateSerializer

    @action(detail=True, methods=['post'])
    def validate(self, request, key=None):
        template = self.get_object()
        try:
            cleaned = validate_spec(
                template, request.data.get('spec', {}),
                partial=bool(request.data.get('draft')),
            )
        except SpecValidationError as exc:
            return Response({'valid': False, 'errors': exc.errors},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({'valid': True, 'spec': cleaned})


class GarmentJobViewSet(viewsets.ModelViewSet):
    serializer_class = GarmentJobSerializer

    def get_queryset(self):
        queryset = GarmentJob.objects.select_related('template').prefetch_related(
            'materials', 'materials__inventory_item'
        )
        queryset = queryset.filter(
            order__in=visible_orders(Order.objects.all(), self.request.user))
        if order_id := self.request.query_params.get('order'):
            queryset = queryset.filter(order__order_id=order_id)
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['draft'] = str(self.request.data.get('draft', '')).lower() == 'true'
        return context

    @action(detail=True, methods=['post'])
    def materials(self, request, pk=None):
        job = self.get_object()
        serializer = JobMaterialSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(job=job)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path='materials/(?P<material_id>[^/.]+)')
    def remove_material(self, request, pk=None, material_id=None):
        JobMaterial.objects.filter(job_id=pk, id=material_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
