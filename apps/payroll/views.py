"""Payroll endpoints. Owner only, every one of them.

`OwnerOnly` is the existing class from core.permissions -- the same one guarding
stock valuation and cost-per-order, which is exactly the right company for this.
No new permission class: a Master supervises the floor and does not sign off its
wages, and the Phase 2 financial boundary said so before any of this existed.
"""

from django.utils.dateparse import parse_date
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.activities.models import UniversalActivity
from apps.staff.attendance import business_date
from core.permissions import OwnerOnly

from . import services
from .models import PayrollPeriod, PayrollRecord
from .serializers import (
    PayrollPeriodListSerializer, PayrollPeriodSerializer, PayrollRecordSerializer,
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
        requested = parse_date(request.data.get('week') or '')
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


class PayrollRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """Individual payslips. Read-only, owner-only, filterable by week."""

    permission_classes = [OwnerOnly]
    serializer_class = PayrollRecordSerializer
    queryset = PayrollRecord.objects.all()

    def get_queryset(self):
        queryset = PayrollRecord.objects.select_related('period', 'staff')
        period = self.request.query_params.get('period')
        if period:
            queryset = queryset.filter(period_id=period)
        staff = self.request.query_params.get('staff')
        if staff:
            queryset = queryset.filter(staff_id=staff)
        return queryset
