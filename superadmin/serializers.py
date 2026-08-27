from rest_framework import serializers

from tenants.models import DemoRequest

from .metrics import tenant_metrics


class TenantSerializer(serializers.Serializer):

    schema_name = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    owner_email = serializers.EmailField(read_only=True)
    created_on = serializers.DateField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    def to_representation(self, tenant):
        metrics = tenant_metrics(tenant)
        return {
            'schema_name': tenant.schema_name,
            'name': tenant.name,
            'owner_email': tenant.owner_email,
            'created_on': tenant.created_on,
            'is_active': tenant.is_active,
            'staff': metrics['staff'],
            'customers': metrics['customers'],
            'orders': metrics['orders'],
            'open_orders': metrics['open_orders'],
            'revenue': float(metrics['revenue'] or 0) if metrics['healthy'] else None,
            'collected': float(metrics['collected'] or 0) if metrics['healthy'] else None,
            'last_order': metrics['last_order'],
            'healthy': metrics['healthy'],
        }


class LeadSerializer(serializers.ModelSerializer):

    class Meta:
        model = DemoRequest
        fields = ['id', 'created_at', 'name', 'boutique', 'email', 'phone',
                  'makes', 'orders_per_month', 'people', 'problem',
                  'status', 'notes']
        read_only_fields = ['id', 'created_at', 'name', 'boutique', 'email',
                            'phone', 'makes', 'orders_per_month', 'people',
                            'problem']
