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

from .models import Payout, PayrollPeriod, PayrollRecord, StaffAdvance, StaffLedgerEntry


class PayrollRecordSerializer(serializers.ModelSerializer):
    """One person's week, with the evidence attached."""

    rate_missing = serializers.BooleanField(read_only=True)
    blocks_approval = serializers.BooleanField(read_only=True)
    worked_hours = serializers.SerializerMethodField()
    payout = serializers.SerializerMethodField()

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
            'advance_recovered_from', 'advance_scheduled', 'advance_recovered',
            'advance_unrecovered', 'advance_balance_before', 'advance_balance_after',
            'net_payable', 'paid_at', 'payout',
        ]
        read_only_fields = fields

    def get_payout(self, instance):
        payout = getattr(instance, 'payout', None)
        return PayoutSerializer(payout).data if payout else None

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


class PayoutSerializer(serializers.ModelSerializer):
    """What was paid, how, and by whom. Read-only: the amount is never typed."""

    method_display = serializers.CharField(source='get_method_display', read_only=True)

    class Meta:
        model = Payout
        fields = ['id', 'payroll_record', 'staff', 'staff_name_snapshot', 'amount',
                  'method', 'method_display', 'reference', 'note', 'paid_at',
                  'created_at']
        read_only_fields = fields


class StaffAdvanceSerializer(serializers.ModelSerializer):
    """An advance and its live position.

    Writable only on creation, and only the terms: staff, amount, date, reason
    and the weekly rule. Everything financial about it afterwards is read from
    the ledger. `weekly_recovery` is the one field an owner may change later,
    through the update path, and it applies to future weeks only.
    """

    issued = serializers.SerializerMethodField()
    recovered = serializers.SerializerMethodField()
    outstanding = serializers.SerializerMethodField()
    entries = serializers.SerializerMethodField()

    class Meta:
        model = StaffAdvance
        fields = ['id', 'staff', 'staff_name_snapshot', 'amount', 'weekly_recovery',
                  'issued_on', 'reason', 'status', 'created_at',
                  'cancelled_at', 'cancel_reason',
                  'issued', 'recovered', 'outstanding', 'entries']
        read_only_fields = ['id', 'staff_name_snapshot', 'status', 'created_at',
                            'cancelled_at', 'cancel_reason']

    def _state(self, instance):
        from .advances import advance_state
        if not hasattr(instance, '_advance_state'):
            instance._advance_state = advance_state(instance)
        return instance._advance_state

    def get_issued(self, instance):
        return str(self._state(instance)['issued'])

    def get_recovered(self, instance):
        return str(self._state(instance)['recovered'])

    def get_outstanding(self, instance):
        return str(self._state(instance)['outstanding'])

    def get_entries(self, instance):
        # The full ledger only on a detail read; a list of forty advances must
        # not fan out into forty ledger scans.
        if not self.context.get('with_entries'):
            return None
        from .advances import ledger_for
        return StaffLedgerEntrySerializer(ledger_for(instance), many=True).data

    def validate_amount(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError('An advance must be a positive amount.')
        return value

    def validate_weekly_recovery(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('Weekly recovery cannot be negative.')
        return value

    def update(self, instance, validated_data):
        """Only the repayment rule may change, and only for the future.

        Amount, date, staff and reason are the historical fact of the advance;
        the ledger already holds them and a later edit would make the row and
        the ledger disagree.
        """
        from .advances import AdvanceError, set_weekly_recovery
        weekly = validated_data.get('weekly_recovery')
        if weekly is None:
            return instance
        try:
            return set_weekly_recovery(instance, weekly, user=self.context['request'].user)
        except AdvanceError as exc:
            raise serializers.ValidationError({'weekly_recovery': str(exc)})
