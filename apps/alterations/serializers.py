"""Serializers for the alteration API.

Follows the shapes the rest of this product already uses: a light list
serializer, a fat detail serializer with nested children, and thin
`serializers.Serializer` classes for write payloads so that validation errors
come back in DRF's usual field-keyed form.
"""

from decimal import Decimal

from rest_framework import serializers

from apps.alterations.models import (
    AlterationActivity,
    AlterationMaterialLine,
    AlterationPayment,
    AlterationRequest,
    AlterationTask,
    AlterationType,
    PaymentMethod,
)
from apps.catalog.models import GarmentJob
from crm_api.models import Customer, Order


class CustomerSummarySerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = ['id', 'first_name', 'last_name', 'name', 'mobile_number', 'email_address']

    def get_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip()


class OrderSummarySerializer(serializers.ModelSerializer):
    """The original order, read-only in every direction.

    Deliberately excludes every financial field the alteration must not touch,
    so nothing downstream can be tempted to write one back.
    """

    class Meta:
        model = Order
        fields = ['id', 'order_id', 'order_status', 'order_date', 'estimated_delivery']
        read_only_fields = fields


class GarmentJobSummarySerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source='template.name', read_only=True)

    class Meta:
        model = GarmentJob
        fields = ['id', 'template_name', 'spec', 'sequence']
        read_only_fields = fields


class AlterationTaskSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.CharField(source='assigned_to.name', read_only=True)
    assigned_to_role = serializers.CharField(source='assigned_to.role', read_only=True)

    class Meta:
        model = AlterationTask
        fields = [
            'id', 'title', 'stage_key', 'status', 'assigned_to', 'assigned_to_name',
            'assigned_to_role', 'notes', 'sequence', 'started_at', 'completed_at',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields


class AlterationActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = AlterationActivity
        fields = [
            'id', 'event_type', 'performed_by', 'performed_by_name',
            'from_status', 'to_status', 'metadata', 'timestamp',
        ]
        read_only_fields = fields


class AlterationPaymentSerializer(serializers.ModelSerializer):
    payment_method_display = serializers.CharField(
        source='get_payment_method_display', read_only=True)

    class Meta:
        model = AlterationPayment
        fields = [
            'id', 'amount', 'payment_method', 'payment_method_display',
            'transaction_reference', 'status', 'received_by', 'received_by_name',
            'received_at', 'notes', 'created_at',
        ]
        read_only_fields = fields


class AlterationMaterialLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlterationMaterialLine
        fields = [
            'id', 'item', 'material_name', 'quantity', 'unit', 'stock_movement',
            'recorded_by', 'recorded_by_name', 'remarks', 'created_at',
        ]
        read_only_fields = fields


class _BalanceMixin:
    def get_outstanding_balance(self, obj):
        from domains.alterations.services import calculate_outstanding_balance
        return str(calculate_outstanding_balance(obj))


class AlterationRequestListSerializer(_BalanceMixin, serializers.ModelSerializer):
    """Everything the alterations register needs, and nothing more."""

    customer = CustomerSummarySerializer(read_only=True)
    original_order = OrderSummarySerializer(read_only=True)
    garment_job = GarmentJobSummarySerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    alteration_type_display = serializers.CharField(
        source='get_alteration_type_display', read_only=True)
    assigned_to_name = serializers.SerializerMethodField()
    outstanding_balance = serializers.SerializerMethodField()

    class Meta:
        model = AlterationRequest
        fields = [
            'id', 'alteration_number', 'customer', 'original_order', 'garment_job',
            'alteration_type', 'alteration_type_display', 'issue_description',
            'status', 'status_display', 'assigned_to_name',
            'charge_amount', 'amount_paid', 'outstanding_balance',
            'received_at', 'completed_at', 'cancelled_at', 'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_assigned_to_name(self, obj):
        for task in obj.tasks.all():
            if task.assigned_to_id:
                return task.assigned_to.name
        return None


class AlterationRequestDetailSerializer(AlterationRequestListSerializer):
    tasks = AlterationTaskSerializer(many=True, read_only=True)
    activities = AlterationActivitySerializer(many=True, read_only=True)
    payments = AlterationPaymentSerializer(many=True, read_only=True)
    material_lines = AlterationMaterialLineSerializer(many=True, read_only=True)
    #: What the *current* user may do right now, derived from the same state
    #: machine the server enforces -- so the UI never has to re-implement it.
    available_actions = serializers.SerializerMethodField()

    class Meta(AlterationRequestListSerializer.Meta):
        fields = AlterationRequestListSerializer.Meta.fields + [
            'requested_adjustments', 'inspection_notes', 'inspection_adjustments',
            'notes', 'tasks', 'activities', 'payments', 'material_lines',
            'available_actions',
        ]
        read_only_fields = fields

    def get_available_actions(self, obj):
        from domains.alterations.workflow import available_actions
        return available_actions(
            obj,
            self.context.get('role'),
            self.context.get('tailor_id'),
        )


# ---------------------------------------------------------------------------
# write payloads
# ---------------------------------------------------------------------------

class AlterationRequestCreateSerializer(serializers.Serializer):
    customer_id = serializers.UUIDField()
    #: Either the numeric pk or the human 'T2B-...' identifier.
    order_id = serializers.CharField()
    garment_job_id = serializers.UUIDField()
    alteration_type = serializers.ChoiceField(
        choices=AlterationType.choices, default=AlterationType.PAID_CLIENT_REQUEST)
    issue_description = serializers.CharField(required=False, allow_blank=True, default='')
    requested_adjustments = serializers.JSONField(required=False, default=dict)
    charge_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, default=Decimal('0.00'))
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class InspectionSerializer(serializers.Serializer):
    inspection_notes = serializers.CharField(required=False, allow_blank=True, default='')
    adjustments = serializers.JSONField(required=False, default=dict)


class SubmitForApprovalSerializer(serializers.Serializer):
    charge_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class AssignSerializer(serializers.Serializer):
    tailor_id = serializers.IntegerField()
    title = serializers.CharField(required=False, allow_blank=True, default='')
    stage_key = serializers.CharField(required=False, allow_blank=True, default='')
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class NotesSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    task_id = serializers.UUIDField(required=False, allow_null=True)


class ReasonSerializer(serializers.Serializer):
    """QC failure and cancellation both refuse to proceed without a reason."""

    reason = serializers.CharField(allow_blank=False)


class RecordPaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    payment_method = serializers.ChoiceField(
        choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    transaction_reference = serializers.CharField(
        required=False, allow_blank=True, default='')
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class RecordMaterialSerializer(serializers.Serializer):
    item_id = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit = serializers.CharField(required=False, allow_blank=True, default='')
    remarks = serializers.CharField(required=False, allow_blank=True, default='')
