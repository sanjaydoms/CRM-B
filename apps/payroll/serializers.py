"""Payroll's own serializers. Nothing here is reachable from another module's.

Deliberately not fields='__all__', and deliberately not reached through
TailorSerializer or StaffProfileSerializer. Those two are readable by the floor;
these carry what everyone earns. Keeping the classes separate means there is no
path -- present or accidental future one -- from a roster request to a wage.

Every field is read-only. Payroll is written by the calculation service through
its own named actions, so a writable serializer would be a way to type a number
into a record instead of earning it.
"""

from rest_framework import serializers

from .models import PayrollPeriod, PayrollRecord


class PayrollRecordSerializer(serializers.ModelSerializer):
    """One person's week, with the evidence attached."""

    rate_missing = serializers.BooleanField(read_only=True)
    blocks_approval = serializers.BooleanField(read_only=True)
    worked_hours = serializers.SerializerMethodField()

    class Meta:
        model = PayrollRecord
        fields = [
            'id', 'period', 'staff', 'staff_name_snapshot', 'staff_role_snapshot',
            'hourly_rate_snapshot', 'worked_minutes', 'regular_minutes',
            'worked_hours', 'gross_earnings',
            'open_session_count', 'has_overlap', 'rate_missing', 'blocks_approval',
            'session_breakdown', 'status', 'approved_at', 'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_worked_hours(self, instance):
        """Hours and minutes for display only.

        The pay is computed from `worked_minutes` server-side; this is a
        convenience for the interface and is never the basis of a figure.
        """
        return {'hours': instance.worked_minutes // 60,
                'minutes': instance.worked_minutes % 60}


class PayrollPeriodSerializer(serializers.ModelSerializer):
    """A week, its totals, and -- on request -- its records."""

    records = PayrollRecordSerializer(many=True, read_only=True)
    totals = serializers.SerializerMethodField()

    class Meta:
        model = PayrollPeriod
        fields = [
            'id', 'period_start', 'period_end', 'status',
            'created_at', 'approved_at', 'totals', 'records',
        ]
        read_only_fields = fields

    def get_totals(self, instance):
        from .services import period_totals
        totals = period_totals(instance)
        # Decimal is not JSON, and float would undo the exactness the whole
        # module is built on. A string keeps the two places intact over the wire.
        totals['total_gross'] = str(totals['total_gross'])
        return totals


class PayrollPeriodListSerializer(PayrollPeriodSerializer):
    """The index. Totals without the per-person rows behind them."""

    class Meta(PayrollPeriodSerializer.Meta):
        fields = [
            'id', 'period_start', 'period_end', 'status',
            'created_at', 'approved_at', 'totals',
        ]
        read_only_fields = fields
