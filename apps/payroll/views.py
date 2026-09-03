"""Payroll endpoints. Owner only, every one of them.

`OwnerOnly` is the existing class from core.permissions -- the same one guarding
stock valuation and cost-per-order, which is exactly the right company for this.
No new permission class: a Master supervises the floor and does not sign off its
wages, and the Phase 2 financial boundary said so before any of this existed.
"""

import uuid

from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError as DRFValidationError
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.activities.models import UniversalActivity
from apps.staff.attendance import business_date
from apps.staff.models import StaffProfile
from core.permissions import OwnerOnly, OwnerOrOwnFinancialRecord
from core.roles import OWNER, resolve_user_role
from crm_api.models import Tailor

from . import advances, deposits, payouts, services
from .models import PayrollPeriod, PayrollRecord, StaffAdvance, StaffLedgerEntry
from .serializers import (
    DepositSummarySerializer, PayoutSerializer, PayrollPeriodListSerializer,
    PayrollPeriodSerializer, PayrollRecordSerializer, StaffAdvanceSerializer,
)


def _log(request, action_name, period, title, extra=None):
    """Record a payroll event on the existing activity feed.

    References the period by id and reports COUNTS ONLY. No money of any kind
    goes in here -- not an individual's earnings and not the week's total.

    UniversalActivity is readable by Owner AND Master (apps/activities/views.py
    scopes it to OWNER plus SUPERVISOR_ROLES), while every payroll endpoint is
    Owner-only. Writing the total gross here would therefore have handed a
    supervisor the boutique's whole wage bill through the audit feed -- the
    payroll access the phase boundary explicitly withholds from them, reached by
    a side door. The period id is enough for an owner to open the run itself.
    """
    user = request.user if request.user.is_authenticated else None
    UniversalActivity.objects.create(
        user=user,
        user_name_snapshot=(
            (user.get_full_name() or user.username) if user else 'System'),
        module='staff',
        entity_type='PayrollPeriod',
        entity_id=str(period.id),
        action=action_name,
        title=title,
        description=f"Week {period.period_start} to {period.period_end}",
        new_value=extra or {},
    )


class PayrollPeriodViewSet(viewsets.ReadOnlyModelViewSet):
    """Weekly payroll runs.

    Read-only at the router: a period is created by `generate` and closed by
    `approve`, both of which have rules a PUT could not express. There is no
    destroy, because deleting an approved payroll run is not a thing this
    product should be able to do.
    """

    permission_classes = [OwnerOnly]
    queryset = PayrollPeriod.objects.all()

    def get_serializer_class(self):
        return (PayrollPeriodListSerializer if self.action == 'list'
                else PayrollPeriodSerializer)

    def get_queryset(self):
        # No tenant filter, and that is correct rather than an omission:
        # django-tenants has already put the connection in one boutique's
        # schema, so this queryset cannot see another's rows. A boutique id
        # from the client would be a way to try.
        return PayrollPeriod.objects.prefetch_related('records').all()

    @action(detail=False, methods=['POST'])
    def generate(self, request):
        """Build or rebuild the draft payroll for a week.

        `week` is any date inside the week; the server resolves it to the
        boutique's Monday. Sending a date rather than a period id is what makes
        this safely repeatable -- there is no id to guess, and the same input
        always names the same week.
        """
        # parse_date RAISES on a well-formed but impossible date and returns
        # None only on a malformed one, so this was a 500 on {"week":
        # "2026-02-30"}. The try/except below catches PayrollError only, and
        # the raise happens before services.generate is ever reached.
        try:
            requested = parse_date(request.data.get('week') or '')
        except ValueError:
            return Response({'error': 'That is not a real date.'},
                            status=status.HTTP_400_BAD_REQUEST)
        day = requested or business_date(timezone.now())
        try:
            period = services.generate(day, user=request.user)
        except services.PayrollError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        totals = services.period_totals(period)
        _log(request, 'PAYROLL_GENERATED', period,
             f'Payroll drafted for week of {period.period_start}',
             extra={'staff_count': totals['staff_count'],
                    'total_minutes': totals['total_minutes'],
                    'blocked_count': totals['blocked_count']})
        return Response(PayrollPeriodSerializer(period).data,
                        status=status.HTTP_200_OK)

    @action(detail=True, methods=['POST'])
    def approve(self, request, pk=None):
        """Freeze the week.

        Period-level rather than the per-record approval the brief sketched.
        A half-approved week has no coherent meaning: regeneration would have to
        skip some rows and rewrite others, the total on screen would describe a
        mixture, and the confirmation the owner is shown ("8 staff, Rs.42,500")
        is itself a statement about the whole week. One period, one signature.
        Each record still carries its own status, approver and timestamp, so the
        per-row history the brief asked to preserve is preserved.
        """
        period = self.get_object()
        try:
            period = services.approve(period, user=request.user)
        except services.PayrollError as exc:
            # 409, not 400: the request was well formed and the caller is not
            # confused -- the world moved underneath them, which is exactly what
            # a second browser tab pressing Approve looks like.
            return Response({'error': str(exc)},
                            status=status.HTTP_409_CONFLICT)

        totals = services.period_totals(period)
        _log(request, 'PAYROLL_APPROVED', period,
             f'Payroll approved for week of {period.period_start}',
             extra={'staff_count': totals['staff_count']})
        return Response(PayrollPeriodSerializer(period).data)


def _own_staff(user):
    return getattr(user, 'tailor_profile', None)


class PayrollRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """Individual payslips.

    The owner reads every one and records payouts. A staff member reads their
    own -- and ONLY their own: the `staff` filter is not honoured for them,
    because reading it would let a tailor name a colleague by id. A Master
    resolves as a plain non-owner here and sees nothing that is not theirs.
    """

    permission_classes = [OwnerOrOwnFinancialRecord]
    serializer_class = PayrollRecordSerializer
    queryset = PayrollRecord.objects.all()

    def get_queryset(self):
        queryset = PayrollRecord.objects.select_related(
            'period', 'staff', 'advance_recovered_from', 'payout')
        if resolve_user_role(self.request.user) != OWNER:
            mine = _own_staff(self.request.user)
            return queryset.filter(staff=mine) if mine else queryset.none()
        # Parsed before the ORM sees them. `?staff=abc` reached
        # IntegerField.get_prep_value and `?period=abc` reached UUIDField, and
        # both raise exceptions DRF does not convert -- so a malformed query
        # string on the payroll surface was a 500 rather than an empty page.
        # Owner-only, so this was never an escalation; it is the "no security
        # probe should produce an unexpected 500" rule.
        period = self.request.query_params.get('period')
        if period:
            try:
                queryset = queryset.filter(period_id=uuid.UUID(str(period)))
            except (TypeError, ValueError, AttributeError):
                return queryset.none()
        staff = self.request.query_params.get('staff')
        if staff:
            try:
                queryset = queryset.filter(staff_id=int(staff))
            except (TypeError, ValueError):
                return queryset.none()
        return queryset

    @action(detail=True, methods=['POST'], url_path='payout')
    def payout(self, request, pk=None):
        """Owner records that this approved payslip was paid.

        Owner-only explicitly, over and above the class permission: a staff
        member may READ their own record and must never be able to mark it
        paid. The amount is never read from the body -- it is the record's own
        net_payable, copied inside the payout transaction.
        """
        if resolve_user_role(request.user) != OWNER:
            return Response({'error': 'Only the boutique owner can record a payout.'},
                            status=status.HTTP_403_FORBIDDEN)
        record = self.get_object()
        try:
            payout = payouts.record_payout(
                record, user=request.user,
                method=request.data.get('method'),
                reference=request.data.get('reference', ''),
                note=request.data.get('note', ''))
        except payouts.PayoutError as exc:
            # 409 for "already paid" and "not approved": the request is well
            # formed and the world is simply not in the state it assumed.
            return Response({'error': str(exc)}, status=status.HTTP_409_CONFLICT)

        _log(request, 'PAYOUT_RECORDED', record.period,
             f'Payroll payout recorded for week of {record.period.period_start}',
             extra={'method': payout.method})
        record.refresh_from_db()
        return Response(PayrollRecordSerializer(record).data)


class DepositViewSet(viewsets.ViewSet):
    """Security deposit positions. Owner only, like everything else here.

    Read-only by construction -- there is no create, update or destroy, because
    a deposit is not something you type. An agreement appears when the owner sets
    the terms on the employment profile; a recovery appears when a payroll is
    approved. Both write the ledger as a consequence of an action that already
    has its own rules and its own audit, which is what keeps the history
    trustworthy.
    """

    permission_classes = [OwnerOnly]

    def list(self, request):
        """Every staff member who has a deposit, with what is left to recover."""
        # Driven by the LEDGER, not by StaffProfile. Keying this on the profile
        # would mean deleting somebody's employment terms hid an obligation they
        # still owed -- the ledger is the authority on what is owed, so it is
        # the ledger that decides who appears here.
        staff_ids = (StaffLedgerEntry.objects
                     .filter(entry_type=StaffLedgerEntry.EntryType.DEPOSIT_AGREED,
                             staff__isnull=False)
                     .values_list('staff_id', flat=True).distinct())
        weekly_by_staff = dict(
            StaffProfile.objects.filter(staff_id__in=staff_ids)
            .values_list('staff_id', 'deposit_weekly'))

        summaries = []
        for staff in Tailor.objects.filter(id__in=staff_ids).order_by('name'):
            state = deposits.deposit_state(staff)
            if state['agreed'] <= 0 and state['recovered'] <= 0:
                continue
            summaries.append({
                'staff': staff.id,
                'staff_name': staff.name,
                'weekly': weekly_by_staff.get(staff.id, 0),
                'entries': [],
                **state,
            })
        return Response(DepositSummarySerializer(summaries, many=True).data)

    def retrieve(self, request, pk=None):
        """One staff member's deposit, with the whole ledger behind it."""
        # int() first: Tailor.id is an AutoField, so a non-numeric id reaches
        # Postgres as a bad cast and surfaces as a 500 rather than the 404 it
        # is. The same guard assign_stage already carries.
        try:
            staff = Tailor.objects.filter(pk=int(pk)).first()
        except (TypeError, ValueError):
            staff = None
        if staff is None:
            return Response({'error': 'Staff member not found.'},
                            status=status.HTTP_404_NOT_FOUND)
        profile = getattr(staff, 'staff_profile', None)
        state = deposits.deposit_state(staff)
        payload = {
            'staff': staff.id,
            'staff_name': staff.name,
            'weekly': profile.deposit_weekly if profile else 0,
            'entries': deposits.ledger_for(staff),
            **state,
        }
        return Response(DepositSummarySerializer(payload).data)


class StaffAdvanceViewSet(viewsets.ModelViewSet):
    """Advances: money lent ahead of payroll, and what has come back.

    The owner does everything. A staff member reads their own advances -- the
    amount, what has been recovered, what is left -- and nothing about anyone
    else's. Masters are non-owners here.

    No destroy. An advance is history from the moment it is written; the way
    to undo one entered in error is `cancel`, which writes a reversal row and
    leaves the mistake readable.
    """

    permission_classes = [OwnerOrOwnFinancialRecord]
    serializer_class = StaffAdvanceSerializer
    queryset = StaffAdvance.objects.all()
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        queryset = StaffAdvance.objects.select_related('staff')
        if resolve_user_role(self.request.user) != OWNER:
            mine = _own_staff(self.request.user)
            return queryset.filter(staff=mine) if mine else queryset.none()
        staff = self.request.query_params.get('staff')
        if staff:
            try:
                queryset = queryset.filter(staff_id=int(staff))
            except (TypeError, ValueError):
                return queryset.none()
        if self.request.query_params.get('active') == 'true':
            queryset = queryset.filter(status=StaffAdvance.Status.ACTIVE)
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['with_entries'] = self.action == 'retrieve'
        return context

    def perform_create(self, serializer):
        """Owner issues an advance. Goes through the service, which writes the
        ledger row in the same transaction -- the serializer never saves alone."""
        staff = serializer.validated_data.get('staff')
        if staff is None:
            raise DRFValidationError({'staff': 'Name the staff member.'})
        try:
            advance = advances.issue(
                staff, serializer.validated_data['amount'],
                user=self.request.user,
                issued_on=serializer.validated_data.get('issued_on'),
                reason=serializer.validated_data.get('reason', ''),
                weekly_recovery=serializer.validated_data.get('weekly_recovery') or 0)
        except advances.AdvanceError as exc:
            raise DRFValidationError({'error': str(exc)})
        serializer.instance = advance
        _log_advance(self.request, 'ADVANCE_ISSUED', advance, 'Advance issued')

    @action(detail=True, methods=['POST'])
    def cancel(self, request, pk=None):
        """Reverse an advance entered in error, before anything is recovered."""
        if resolve_user_role(request.user) != OWNER:
            return Response({'error': 'Only the boutique owner can cancel an advance.'},
                            status=status.HTTP_403_FORBIDDEN)
        advance = self.get_object()
        try:
            advance = advances.cancel(
                advance, user=request.user, reason=request.data.get('reason', ''))
        except advances.AdvanceError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        _log_advance(request, 'ADVANCE_CANCELLED', advance, 'Advance cancelled')
        return Response(StaffAdvanceSerializer(
            advance, context={'with_entries': True}).data)


def _log_advance(request, action_name, advance, title):
    """No amount and no name -- Masters read this feed.

    Even "who got an advance" is a fact about a colleague's finances, so the
    title says only that one was issued or cancelled; the entity_id lets the
    owner open it.
    """
    user = request.user if request.user.is_authenticated else None
    UniversalActivity.objects.create(
        user=user,
        user_name_snapshot=(
            (user.get_full_name() or user.username) if user else 'System'),
        module='staff',
        entity_type='StaffAdvance',
        entity_id=str(advance.id),
        action=action_name,
        title=title,
        description='',
        new_value={'status': advance.status},
    )
