from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import status, views, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.activities.models import UniversalActivity
from core import formatting as core_formatting
from core.permissions import SUPERVISOR_ROLES, StaffSelfOrOwner
from core.roles import OWNER, resolve_user_role
from crm_api.models import Tailor

from . import attendance
from .models import AttendanceSession, StaffProfile
from .serializers import AttendanceSessionSerializer, StaffProfileSerializer


def _aware(moment):
    """Attach the boutique's timezone to a naive timestamp the owner typed.

    The owner's form sends a local wall-clock time with no offset ("09:10 on
    Sep 1"), and USE_TZ is on, so storing it unchanged would have Django read it
    as UTC -- filing an Indian boutique's 09:10 start as 14:40 local and putting
    an early shift on the wrong day of the timesheet. An offset that IS supplied
    is respected; only a naive value is interpreted, and it is interpreted the
    way the person typing it meant.
    """
    if moment is None or timezone.is_aware(moment):
        return moment
    return moment.replace(tzinfo=core_formatting.tenant_timezone())


class StaffProfileViewSet(viewsets.ModelViewSet):
    """Employment terms for the boutique's roster.

    Three layers guard this, and the pairing is the point:

      StaffSelfOrOwner   what a caller may DO -- only the owner writes.
      get_queryset       which rows EXIST for them.
      the serializer     which FIELDS of a visible row they may read.

    The third layer is what lets a Master supervise without being paid to
    supervise: they can see who is on the team and when they joined, and the
    money on someone else's row is removed on the way out. Scoping alone could
    not express that -- a row is either in the queryset or it is not.

    A tailor asking for a colleague's profile by id gets a 404 rather than a
    403, because DRF resolves the object through this queryset. The row is not
    hidden behind a refusal; it is simply not in their world, which is also the
    convention `visible_orders` already sets for the order book.
    """

    serializer_class = StaffProfileSerializer
    permission_classes = [StaffSelfOrOwner]

    @transaction.atomic
    def perform_create(self, serializer):
        profile = serializer.save()
        self._record_deposit_agreement(profile, None)

    @transaction.atomic
    def perform_update(self, serializer):
        was = serializer.instance.deposit_total
        profile = serializer.save()
        self._record_deposit_agreement(profile, was)

    def _record_deposit_agreement(self, profile, previous):
        """Give a changed deposit figure a line in the staff ledger.

        The agreement lives on this model because that is where the owner sets
        it, but a number in a column cannot answer "why does this person owe
        5,000, and since when". Writing a ledger row on the way past means the
        history exists without the owner having to do anything extra, and
        without a second screen for entering the same fact twice.

        Only on an actual CHANGE: re-saving a profile to correct a phone number
        must not append an identical agreement row, and a boutique that takes no
        deposits should have no deposit history at all.

        A change TO zero is a change, and writing it is the whole point. Setting
        the agreed deposit to nothing is how an owner cancels one, and treating
        that as "no deposit, nothing to record" would leave the ledger holding
        the old agreement -- so payroll would go on recovering money against a
        deposit the owner had just cancelled, with no way to stop it.

        Atomic with the profile save (see the decorators above): a ledger write
        that failed on its own would leave the terms changed with no history of
        it, and the equality guard means no later save would ever repair that.

        Writes are already Owner-only (StaffSelfOrOwner), so reaching this means
        the owner did it.
        """
        from apps.payroll import deposits
        current = profile.deposit_total or 0
        if previous is None:
            # Creation: only worth a row if there is actually a deposit.
            if current <= 0:
                return
        elif previous == current:
            return

        deposits.record_agreement(
            profile.staff, current, user=self.request.user,
            note=('Security deposit agreed' if previous in (None, 0)
                  else 'Security deposit cancelled' if current <= 0
                  else 'Security deposit terms changed'))

    def get_queryset(self):
        """Owner and supervisors see the roster; everyone else sees their own row.

        `SUPERVISOR_ROLES` is imported rather than restated. It is the same
        frozenset that decides who sees the whole order book in
        `visible_orders`, and a boutique that promotes a role to supervisor
        should not have to remember that Staff Management keeps its own list.

        `select_related('staff')` because the serializer reads `staff.name` and
        `staff.role` on every row -- without it a roster of twenty staff is
        twenty-one queries.
        """
        queryset = StaffProfile.objects.select_related('staff')
        role = resolve_user_role(self.request.user)
        if role == OWNER or role in SUPERVISOR_ROLES:
            return queryset

        # Everyone else: their own profile, reached through the Tailor row their
        # login is attached to. An account with no roster profile -- a
        # design-only designer, an orphaned login -- matches nothing, which is
        # the right answer rather than an error.
        profile = getattr(self.request.user, 'tailor_profile', None)
        if profile is None:
            return queryset.none()
        return queryset.filter(staff=profile)


def _staff_for(user):
    """The roster row this login belongs to, or None."""
    return getattr(user, 'tailor_profile', None)


def _is_owner(user):
    return resolve_user_role(user) == OWNER


def _can_see_team(user):
    role = resolve_user_role(user)
    return role == OWNER or role in SUPERVISOR_ROLES


def _log(request, action, session, title, before=None, after=None):
    """Record a staff event on the existing cross-module activity feed.

    UniversalActivity rather than a table of our own: it already carries an
    actor, a name snapshot that outlives the account, old_value/new_value, and a
    read-only viewset the owner can already reach. A second audit log would be a
    second place to look.
    """
    user = request.user if request.user.is_authenticated else None
    UniversalActivity.objects.create(
        user=user,
        user_name_snapshot=(
            (user.get_full_name() or user.username) if user else 'System'),
        module='staff',
        entity_type='AttendanceSession',
        entity_id=str(session.id),
        action=action,
        title=title,
        description=f"{session.staff.name} on {session.date}",
        old_value=before or {},
        new_value=after or {},
    )


class AttendanceSessionViewSet(viewsets.ReadOnlyModelViewSet):
    """Attended time: who was at work, when, and for how long.

    ReadOnly at the router level on purpose. Every write is a named action with
    its own rules, because the writes are not interchangeable: a staff member
    stamping themselves in, an owner entering a day somebody missed, and an
    owner correcting a mistake are three different events with three different
    audit consequences. A generic create/update would collapse them into one and
    lose exactly the distinction a timesheet has to preserve.
    """

    serializer_class = AttendanceSessionSerializer
    permission_classes = [StaffSelfOrOwner]

    def get_queryset(self):
        """Owner and supervisors see the floor; everyone else sees their own days.

        The same scoping StaffProfileViewSet uses, and for the same reason:
        supervising a floor means knowing who is on it. Attendance carries no
        money, so unlike employment terms there is nothing here to strip.
        """
        queryset = AttendanceSession.objects.select_related('staff')
        if _can_see_team(self.request.user):
            staff_id = self.request.query_params.get('staff')
            if staff_id:
                queryset = queryset.filter(staff_id=staff_id)
            day = self.request.query_params.get('date')
            if day:
                queryset = queryset.filter(date=day)
            return queryset

        profile = _staff_for(self.request.user)
        if profile is None:
            return queryset.none()
        # NOTE the `staff` parameter is not honoured on this branch. Reading it
        # here would let a tailor ask for a colleague by id; their own profile
        # is the only staff row this branch can ever name.
        return queryset.filter(staff=profile)

    @action(detail=False, methods=['GET'])
    def current(self, request):
        """What the caller's day looks like right now.

        Answers for the signed-in staff member only -- an owner watching the
        floor uses the list endpoint, which is scoped and filterable. Keeping
        this one personal is what lets the phone screen call it with no
        parameters and trust the answer.
        """
        profile = _staff_for(request.user)
        if profile is None:
            return Response(
                {'staff': None, 'state': 'NOT_STAFF', 'session': None},
                status=status.HTTP_200_OK)

        session = attendance.open_session(profile)
        if session is not None:
            return Response({
                'staff': profile.id, 'state': 'WORKING',
                'session': AttendanceSessionSerializer(session).data,
            })

        today = attendance.business_date(timezone.now())
        finished = AttendanceSession.objects.filter(
            staff=profile, date=today, check_out__isnull=False
        ).order_by('-check_out').first()
        return Response({
            'staff': profile.id,
            'state': 'CHECKED_OUT' if finished else 'NOT_CHECKED_IN',
            'session': (AttendanceSessionSerializer(finished).data
                        if finished else None),
            'today_minutes': sum(
                s.minutes or 0 for s in AttendanceSession.objects.filter(
                    staff=profile, date=today)),
        })

    @action(detail=False, methods=['POST'], url_path='check-in')
    def check_in(self, request):
        """Start the caller's own session. No timestamp is read from the body."""
        profile = _staff_for(request.user)
        if profile is None:
            return Response(
                {'error': 'Your account is not on the staff roster, so it '
                          'cannot record attendance.'},
                status=status.HTTP_403_FORBIDDEN)
        try:
            session = attendance.check_in(
                profile, user=request.user, note=request.data.get('note', ''))
        except attendance.AttendanceError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        _log(request, 'CHECKED_IN', session, f'{profile.name} checked in',
             after={'check_in': str(session.check_in), 'source': session.source})
        return Response(AttendanceSessionSerializer(session).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['POST'], url_path='check-out')
    def check_out(self, request):
        """Close the caller's own session and store its duration."""
        profile = _staff_for(request.user)
        if profile is None:
            return Response(
                {'error': 'Your account is not on the staff roster, so it '
                          'cannot record attendance.'},
                status=status.HTTP_403_FORBIDDEN)
        try:
            session = attendance.check_out(profile, user=request.user)
        except attendance.AttendanceError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        _log(request, 'CHECKED_OUT', session, f'{profile.name} checked out',
             after={'check_out': str(session.check_out), 'minutes': session.minutes})
        return Response(AttendanceSessionSerializer(session).data)

    @action(detail=False, methods=['POST'], url_path='record')
    def record(self, request):
        """Owner enters a shift somebody missed. Marked OWNER, never SELF."""
        if not _is_owner(request.user):
            return Response(
                {'error': 'Only the boutique owner can record attendance for '
                          'someone else.'},
                status=status.HTTP_403_FORBIDDEN)

        staff = Tailor.objects.filter(id=request.data.get('staff')).first()
        if staff is None:
            return Response({'error': 'Staff member not found.'},
                            status=status.HTTP_404_NOT_FOUND)

        check_in_at = parse_datetime(request.data.get('check_in') or '')
        check_out_at = parse_datetime(request.data.get('check_out') or '')
        if check_in_at is None:
            return Response({'error': 'A valid check-in time is required.'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            session = attendance.record_for_staff(
                staff, user=request.user,
                check_in_at=_aware(check_in_at),
                check_out_at=_aware(check_out_at),
                note=request.data.get('note', ''))
        except attendance.AttendanceError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        _log(request, 'ATTENDANCE_RECORDED', session,
             f'Attendance recorded for {staff.name}',
             after={'check_in': str(session.check_in),
                    'check_out': str(session.check_out),
                    'minutes': session.minutes, 'source': session.source})
        return Response(AttendanceSessionSerializer(session).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['POST'], url_path='correct')
    def correct(self, request, pk=None):
        """Owner changes the stamps on a session, with a reason, keeping the original.

        Owner-only, deliberately. A supervisor can see the floor's hours but not
        edit them: these minutes become wages in the next phase, and a manager
        who can quietly add an hour to a timesheet is the conflict the financial
        boundary exists to prevent.
        """
        if not _is_owner(request.user):
            return Response(
                {'error': 'Only the boutique owner can correct attendance.'},
                status=status.HTTP_403_FORBIDDEN)

        session = self.get_object()
        before = {'check_in': str(session.check_in),
                  'check_out': str(session.check_out),
                  'minutes': session.minutes}
        try:
            session = attendance.correct(
                session, user=request.user,
                reason=request.data.get('reason', ''),
                check_in_at=_aware(parse_datetime(request.data.get('check_in') or '')),
                check_out_at=_aware(parse_datetime(request.data.get('check_out') or '')))
        except attendance.AttendanceError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        _log(request, 'ATTENDANCE_CORRECTED', session,
             f'Attendance corrected for {session.staff.name}',
             before=before,
             after={'check_in': str(session.check_in),
                    'check_out': str(session.check_out),
                    'minutes': session.minutes,
                    'reason': session.correction_reason})
        return Response(AttendanceSessionSerializer(session).data)


class TimesheetView(views.APIView):
    """One person's week of attended time, with the totals already added up.

    A plain APIView at its own path, following DashboardView: this is a computed
    report over sessions rather than a view of a resource, and mounting it on the
    attendance router would make it look like one.
    """

    permission_classes = [StaffSelfOrOwner]

    def get(self, request):
        requested = request.query_params.get('staff')

        if _can_see_team(request.user):
            staff = (Tailor.objects.filter(id=requested).first() if requested
                     else _staff_for(request.user))
            if staff is None:
                return Response(
                    {'error': 'Name a staff member to see their timesheet.'},
                    status=status.HTTP_400_BAD_REQUEST)
        else:
            # The `staff` parameter is IGNORED rather than validated for
            # everyone else. Comparing it against the caller's own id would work
            # and would also mean a mismatch leaks whether that id exists; there
            # is nothing to leak if the parameter is never read.
            staff = _staff_for(request.user)
            if staff is None:
                return Response({'error': 'Your account is not on the staff roster.'},
                                status=status.HTTP_403_FORBIDDEN)

        day = parse_date(request.query_params.get('week') or '')
        if day is None:
            day = attendance.business_date(timezone.now())

        sheet = attendance.timesheet(staff, day)
        return Response({
            'staff': staff.id,
            'staff_name': staff.name,
            'staff_role': staff.role,
            'week_start': sheet['week_start'],
            'week_end': sheet['week_end'],
            'total_minutes': sheet['total_minutes'],
            'open_sessions': sheet['open_sessions'],
            'sessions': AttendanceSessionSerializer(sheet['sessions'], many=True).data,
        })
