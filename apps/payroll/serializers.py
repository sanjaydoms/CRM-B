"""Payroll's own serializers. Nothing here is reachable from another module's.

Deliberately not fields='__all__', and deliberately not reached through
TailorSerializer or StaffProfileSerializer. Those two are readable by the floor;
these carry what everyone earns. Keeping the classes separate means there is no
path -- present or accidental future one -- from a roster request to a wage.

Every field is read-only. Payroll is written by the calculation service through
its own named actions, so a writable serializer would be a way to type a number
into a record instead of earning it.
"""

from decimal import Decimal

from rest_framework import serializers

from .models import PayrollPeriod, PayrollRecord, StaffLedgerEntry


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
            'deposit_scheduled', 'deposit_recovered', 'deposit_unrecovered',
            'deposit_balance_before', 'deposit_balance_after',
            'net_before_other_deductions',
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
        # EVERY Decimal, not just the gross. DRF's JSON encoder turns a Decimal
        # it has not been told about into a float, so a total of 500.00 went
        # over the wire as 500.0 -- binary floating point, in a payroll payload,
        # in the one module built entirely on not doing that. Converting the
        # whole set means a total added here later cannot quietly become a float
        # because somebody forgot to name it.
        return {key: str(value) if isinstance(value, Decimal) else value
                for key, value in totals.items()}


class PayrollPeriodListSerializer(PayrollPeriodSerializer):
    """The index. Totals without the per-person rows behind them."""

    class Meta(PayrollPeriodSerializer.Meta):
        fields = [
            'id', 'period_start', 'period_end', 'status',
            'created_at', 'approved_at', 'totals',
        ]
        read_only_fields = fields


class StaffLedgerEntrySerializer(serializers.ModelSerializer):
    """One line of financial history. Read-only, always.

    There is no write path to this model over HTTP and there must not be one.
    Agreements are written as a side effect of the owner setting the terms;
    recoveries are written by payroll approval. A ledger somebody can POST to is
    not a ledger.
    """

    entry_type_display = serializers.CharField(
        source='get_entry_type_display', read_only=True)

    class Meta:
        model = StaffLedgerEntry
        fields = [
            'id', 'staff', 'staff_name_snapshot', 'entry_type',
            'entry_type_display', 'amount', 'balance_before', 'balance_after',
            'payroll_record', 'note', 'created_at',
        ]
        read_only_fields = fields


class DepositSummarySerializer(serializers.Serializer):
    """One staff member's deposit position, as the panel draws it."""

    staff = serializers.IntegerField()
    staff_name = serializers.CharField()
    agreed = serializers.DecimalField(max_digits=12, decimal_places=2)
    recovered = serializers.DecimalField(max_digits=12, decimal_places=2)
    remaining = serializers.DecimalField(max_digits=12, decimal_places=2)
    over_recovered = serializers.DecimalField(max_digits=12, decimal_places=2)
    fully_recovered = serializers.BooleanField()
    weekly = serializers.DecimalField(max_digits=12, decimal_places=2)
    entries = StaffLedgerEntrySerializer(many=True)
