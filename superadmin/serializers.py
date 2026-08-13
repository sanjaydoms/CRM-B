from rest_framework import serializers

from tenants.models import DemoRequest

from .metrics import tenant_metrics


class TenantSerializer(serializers.Serializer):
    """A boutique as the console shows it: the registry row plus what is
    happening inside its schema.

    Not a ModelSerializer. The interesting half of this payload -- every count,
    the revenue and the last-order date -- is not on BoutiqueTenant and cannot
    be: those rows live in another Postgres schema. Declaring the fields plainly
    is shorter than a ModelSerializer with six SerializerMethodFields bolted on.
    """

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
            # Decimal is not JSON, and DRF would render it as a quoted string
            # that the portal then has to parse before it can add anything up.
            'revenue': float(metrics['revenue'] or 0) if metrics['healthy'] else None,
            # BOOKED and CASH are two different numbers (see metrics.py). The
            # console renders both columns and totals both, so omitting this one
            # put an em-dash in every row under a platform total that showed a
            # real figure -- which reads as "no boutique has collected anything".
            'collected': float(metrics['collected'] or 0) if metrics['healthy'] else None,
            'last_order': metrics['last_order'],
            # False means the schema could not be read at all. The portal shows
            # this as a warning rather than as a boutique with no customers,
            # which is what a plain zero would have looked like.
            'healthy': metrics['healthy'],
        }


class LeadSerializer(serializers.ModelSerializer):
    """A demo request from the marketing site.

    Only status and notes are writable. Everything else was typed by a stranger
    and is the evidence of what they actually sent, so it is read-only for the
    same reason it is read-only in the Django admin -- a careless PATCH must not
    be able to rewrite the record of an inbound lead.
    """

    class Meta:
        model = DemoRequest
        fields = ['id', 'created_at', 'name', 'boutique', 'email', 'phone',
                  'makes', 'orders_per_month', 'people', 'problem',
                  'status', 'notes']
        read_only_fields = ['id', 'created_at', 'name', 'boutique', 'email',
                            'phone', 'makes', 'orders_per_month', 'people',
                            'problem']
