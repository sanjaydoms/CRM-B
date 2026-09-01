"""Recording and reading attended time.

The rules live here rather than in the viewset so that "how long did this person
work" has exactly one answer, whoever asks -- the check-out endpoint, the
timesheet, and the payroll phase that will consume this next. `domains/orders/`
sets the same precedent for order money.

Nothing in this module knows about wages. It answers minutes; multiplying them
by a rate is Phase 4's job and belongs somewhere else, so that attendance can
stay a factual record rather than a financial one.
"""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.formatting import to_local

from .models import AttendanceSession


class AttendanceError(ValueError):
    """This attendance action cannot happen, and nothing has been written.

    A ValueError subclass because the view layer already renders ValueError as a
    400 with its message -- and the message is the point: "you are already
    checked in" is actionable, "invalid" is not.
    """


def business_date(moment, tenant=None):
    """The boutique's own calendar date for an instant.

    Timestamps are stored in UTC and rendered in the boutique's timezone (see
    core.formatting), so the UTC date is the wrong thing to file a shift under:
    a 05:30 start in Asia/Kolkata is midnight UTC of the day BEFORE, and an
    evening shift crosses the other way. Every boutique east or west of
    Greenwich would have shifts landing on the wrong day of the timesheet.
    """
    return to_local(moment, tenant).date()


def open_session(staff):
    """The session this person has not finished yet, or None."""
    return AttendanceSession.objects.filter(
        staff=staff, check_out__isnull=True).first()


@transaction.atomic
def check_in(staff, *, user, source=AttendanceSession.Source.SELF, note=''):
    """Start a session. The server stamps the time; the caller does not.

    Deliberately takes no timestamp argument. A check-in time supplied by the
    client is a check-in time the client can choose, and the whole value of this
    record is that it says when somebody was actually there.

    The pre-check gives a readable refusal; the IntegrityError catch is what
    holds when two taps race past it, because the partial unique index is the
    only thing that can decide a tie.
    """
    if open_session(staff) is not None:
        raise AttendanceError(
            f"{staff.name} is already checked in. Check out before starting "
            f"another session.")

    now = timezone.now()
    try:
        return AttendanceSession.objects.create(
            staff=staff, date=business_date(now), check_in=now,
            source=source, note=note or '', recorded_by=user,
        )
    except IntegrityError:
        raise AttendanceError(
            f"{staff.name} is already checked in. Check out before starting "
            f"another session.")


@transaction.atomic
def check_out(staff, *, user):
    """Close the open session and write its duration.

    `select_for_update` because check-out is read-modify-write and a double tap
    would otherwise close the same session twice, the second one recomputing
    minutes against a check_out that had already moved.
    """
    session = AttendanceSession.objects.select_for_update().filter(
        staff=staff, check_out__isnull=True).first()
    if session is None:
        raise AttendanceError(
            f"{staff.name} is not checked in, so there is nothing to check out of.")

    session.check_out = timezone.now()
    session.minutes = session.duration_minutes()
    session.save(update_fields=['check_out', 'minutes', 'updated_at'])
    return session


def record_for_staff(staff, *, user, check_in_at, check_out_at=None, note=''):
    """Enter a shift on somebody's behalf -- the owner filling in a missed day.

    Marked `source=OWNER`, never SELF: a row somebody typed for you and a row
    you stamped yourself are different kinds of evidence, and a timesheet that
    cannot tell them apart is a timesheet nobody can audit.
    """
    if check_in_at is None:
        raise AttendanceError('A check-in time is required.')
    if check_out_at is not None and check_out_at < check_in_at:
        raise AttendanceError('The check-out time is before the check-in time.')
    if check_out_at is None and open_session(staff) is not None:
        raise AttendanceError(
            f"{staff.name} already has an open session. Close it before adding "
            f"another.")

    session = AttendanceSession(
        staff=staff, date=business_date(check_in_at),
        check_in=check_in_at, check_out=check_out_at,
        source=AttendanceSession.Source.OWNER, note=note or '', recorded_by=user,
    )
    session.minutes = session.duration_minutes()
    try:
        session.save()
    except IntegrityError:
        raise AttendanceError(
            f"{staff.name} already has an open session. Close it before adding "
            f"another.")
    return session


def correct(session, *, user, reason, check_in_at=None, check_out_at=None):
    """Change the stamps on an existing session, keeping what they used to say.

    The original pair is captured on the FIRST correction only and never
    rewritten, so "what did this row say before anyone touched it" survives any
    number of later edits. The blow-by-blow of repeated corrections is written
    to UniversalActivity by the caller, which already carries old_value and
    new_value for exactly this purpose.

    A reason is required rather than encouraged. An attendance change that feeds
    somebody's wages and carries no explanation is the thing an audit exists to
    find, and making it optional guarantees it will usually be absent.
    """
    reason = (reason or '').strip()
    if not reason:
        raise AttendanceError('Give a reason for changing this attendance record.')

    new_in = check_in_at or session.check_in
    new_out = check_out_at if check_out_at is not None else session.check_out
    if new_out is not None and new_out < new_in:
        raise AttendanceError('The check-out time is before the check-in time.')

    if session.corrected_at is None:
        session.original_check_in = session.check_in
        session.original_check_out = session.check_out

    session.check_in = new_in
    session.check_out = new_out
    session.date = business_date(new_in)
    session.minutes = session.duration_minutes()
    session.corrected_by = user
    session.corrected_at = timezone.now()
    session.correction_reason = reason
    session.save()
    return session


def week_start(day):
    """The Monday of the week `day` falls in.

    Monday because Python's weekday() already counts from it, and because a
    boutique's week has to start SOMEWHERE that both the timesheet and the
    payroll period agree on. Fixed rather than configurable until somebody asks.
    """
    return day - timedelta(days=day.weekday())


def timesheet(staff, day):
    """One person's week: every session, plus the totals.

    Sessions still open contribute no minutes -- an unfinished shift has no
    duration yet, and counting the elapsed time so far would make the weekly
    total change every time the page was refreshed.
    """
    start = week_start(day)
    end = start + timedelta(days=6)
    sessions = list(AttendanceSession.objects.filter(
        staff=staff, date__gte=start, date__lte=end).order_by('date', 'check_in'))
    return {
        'staff': staff,
        'week_start': start,
        'week_end': end,
        'sessions': sessions,
        'total_minutes': sum(s.minutes or 0 for s in sessions),
        'open_sessions': sum(1 for s in sessions if s.is_open),
    }
