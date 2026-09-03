from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from core.permissions import visible_orders
from crm_api.models import Order
from .models import ProductionTask, QCRecord
from .serializers import ProductionTaskSerializer, QCRecordSerializer
from apps.activities.models import UniversalActivity


def _visible_order_ids(user):
    return visible_orders(Order.objects.all(), user).values('id')


class ProductionTaskViewSet(viewsets.ModelViewSet):
    queryset = ProductionTask.objects.select_related('order', 'order__customer', 'assigned_to').all()
    serializer_class = ProductionTaskSerializer

    def get_queryset(self):
        return super().get_queryset().filter(order_id__in=_visible_order_ids(self.request.user))

    def perform_create(self, serializer):
        task = serializer.save()
        UniversalActivity.objects.create(
            user=self.request.user if self.request.user.is_authenticated else None,
            user_name_snapshot=self.request.user.get_full_name() or self.request.user.username if self.request.user.is_authenticated else "System",
            module="production",
            entity_type="ProductionTask",
            entity_id=str(task.id),
            action="CREATED",
            title=f"Task Created: {task.title}",
            description=f"Task '{task.title}' created for Order {task.order.order_id}",
            new_value={"status": task.status, "assigned_to": task.assigned_to.name if task.assigned_to else None}
        )

    def perform_update(self, serializer):
        old_task = self.get_object()
        old_status = old_task.status
        old_assigned = old_task.assigned_to.name if old_task.assigned_to else None
        
        task = serializer.save()
        
        if old_status != 'COMPLETED' and task.status == 'COMPLETED':
            task.completed_at = timezone.now()
            task.save(update_fields=['completed_at'])

        UniversalActivity.objects.create(
            user=self.request.user if self.request.user.is_authenticated else None,
            user_name_snapshot=self.request.user.get_full_name() or self.request.user.username if self.request.user.is_authenticated else "System",
            module="production",
            entity_type="ProductionTask",
            entity_id=str(task.id),
            action="UPDATED" if old_status == task.status else "STATUS_CHANGED",
            title=f"Task {task.title} → {task.status}",
            description=f"Task '{task.title}' updated on Order {task.order.order_id}",
            old_value={"status": old_status, "assigned_to": old_assigned},
            new_value={"status": task.status, "assigned_to": task.assigned_to.name if task.assigned_to else None}
        )

class QCRecordViewSet(viewsets.ModelViewSet):
    queryset = QCRecord.objects.select_related('order', 'task', 'inspector').all()
    serializer_class = QCRecordSerializer

    def get_queryset(self):
        return super().get_queryset().filter(order_id__in=_visible_order_ids(self.request.user))

    def perform_create(self, serializer):
        qc = serializer.save()
        UniversalActivity.objects.create(
            user=self.request.user if self.request.user.is_authenticated else None,
            user_name_snapshot=self.request.user.get_full_name() or self.request.user.username if self.request.user.is_authenticated else "System",
            module="production",
            entity_type="QCRecord",
            entity_id=str(qc.id),
            action="QC_SUBMITTED",
            title=f"QC Record: {qc.status}",
            description=f"Quality check conducted for Order {qc.order.order_id}. Result: {qc.status}",
            new_value={"status": qc.status, "comments": qc.comments}
        )
