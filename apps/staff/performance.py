"""Operational performance: what the product can honestly say about someone's work.

EVERY METRIC NAMES ITS SOURCE
=============================
    worked hours, attendance days   AttendanceSession        (Phase 3)
    assigned / completed work       OrderStage               (the workflow's own record)
    on time / overdue               OrderStage.sla_hours vs elapsed
    quality / rework                QCRecord  -- SEE BELOW

Nothing here reads a rate, a payslip or a ledger. Performance and compensation
are kept apart on purpose: a Master may see how the floor is working and must
never see what it is paid, and the cleanest way to guarantee that is for this
module to have no access to the numbers at all.

QUALITY IS REPORTED ONLY WHEN QC RECORDS EXIST
=============================================
`QCRecord` can be written: `/api/production/qc/` is a full ModelViewSet with a
`perform_create` (apps/production/views.py). What no part of the product does is
DRIVE it -- no screen posts to that endpoint, so on a boutique that has not
called the API directly the table is empty.

So quality is not "unmeasurable in principle", it is "usually unmeasured in
practice", and the difference matters: this module must not hardcode either
answer. Every quality figure is computed from whatever QCRecords actually exist
for the person and period. With none, the ratios report `available: False` with
a reason -- a rate over an empty table would be a fabrication wearing a
percentage sign. With records present it reports them.

An earlier draft of this module asserted that nothing in the application ever
creates a QCRecord. That was wrong, and the test that "proved" it only counted
rows in an empty test database. Both have been corrected.

WHY OrderStage AND NOT ProductionTask
=====================================
Both record who does what. ProductionTask mirrors the stages and is kept in step
by the workflow, but `ProductionTask.due_date` is null on every row ever created
(nothing sets it), so it cannot support a timeliness metric at all. OrderStage
carries `sla_hours` from the boutique's own workflow_config, plus `started_at`,
`completed_at`, `assigned_to` and `performed_by`. It is the richer record and the
one the workflow actually enforces, so it is the source here.

ELAPSED TIME IS THE RIGHT CLOCK HERE
====================================
Phase 3 established that a stage's wall-clock elapsed time must never be paid as
attendance, because it runs through nights and weekends. Timeliness is the case
where wall-clock is exactly right: `sla_hours` is a promise about how long a
stage may take in real time, so comparing it against real elapsed time is
comparing like with like. The two uses are different questions about the same
column, and only one of them is about money.

NO DATA IS NOT ZERO
===================
A staff member with no assigned work has no completion rate. Reporting 0% would
say they failed to complete work they were never given. Every ratio returns
`available: False` when its denominator is empty, and the interface renders that
as "no data", never as a zero.
"""

from datetime import datetime, time, timedelta, timezone as dt_timezone

from django.db.models import Count, Q
from django.utils import timezone

from crm_api.models import OrderStage
from core.formatting import to_local

from .models import AttendanceSession, StaffProfile

#: Stages that are finished with, one way or another.
SETTLED = ('COMPLETED', 'SKIPPED')

utc = dt_timezone.utc


def _metric(value, available=True, reason=''):
    """One reported figure, with whether it means anything.

    `available` is the whole point of this shape. A caller must not be able to
    read a number without also being told whether there was data behind it.
    """
    return {'value': value, 'available': bool(available), 'reason': reason}


def _unavailable(reason):
    return _metric(None, available=False, reason=reason)


def _ratio(part, whole, reason='No work assigned in this period.'):
    """A percentage, or an explicit absence when the denominator is empty."""
    if not whole:
        return _unavailable(reason)
    return _metric(round((part / whole) * 100, 1))


def effective_window(profile, start, end):
    """The days of this period the person was actually employed for.

    Someone who joined on the Wednesday should not be measured against the whole
    week, and someone who left on the Friday should not be marked absent for the
    days after. Mirrors `apps.payroll.services._payable_window`, which narrows
    the same way for pay -- the two must agree about when an employment existed.
    """
    first, last = start, end
    if profile is not None:
        if profile.joined_at and profile.joined_at > first:
            first = profile.joined_at
        if profile.exit_date and profile.exit_date < last:
            last = profile.exit_date
    return first, last


def attendance_metrics(staff, start, end):
    """Hours and days actually attended. Source: AttendanceSession."""
    # Closed and open rows in ONE read. Counting the open ones separately cost a
    # second query per staff member, which on a team dashboard is a per-person
    # fan-out for a number already present in the rows just fetched.
    every = list(AttendanceSession.objects.filter(
        staff=staff, date__gte=start, date__lte=end))
    sessions = [s for s in every if s.check_out is not None]
    open_count = len(every) - len(sessions)
    if not sessions:
        return {
            'days_attended': _metric(0),
            # Not an available 0: this is the same fact as worked_hours in
            # another unit, and one payload must not answer it both ways.
            # `days_attended` stays a real count, because zero days IS a fact.
            'worked_minutes': _unavailable('No attendance recorded in this period.'),
            'worked_hours': _unavailable('No attendance recorded in this period.'),
            'average_hours_per_day': _unavailable(
                'No attendance recorded in this period.'),
            'open_sessions': _metric(open_count),
        }

    minutes = sum(int(s.minutes or 0) for s in sessions)
    days = len({s.date for s in sessions})
    return {
        'days_attended': _metric(days),
        'worked_minutes': _metric(minutes),
        'worked_hours': _metric(round(minutes / 60, 2)),
        # Per day ATTENDED, not per calendar day: the product has no roster of
        # expected working days, and inventing one would make this a fiction.
        'average_hours_per_day': _metric(round((minutes / 60) / days, 2)),
        'open_sessions': _metric(open_count),
    }


def _stages_in_window(staff, start, end):
    """Just the period's stages, for callers that do not need the backlog."""
    in_window, _open = _stages_for(staff, start, end)
    return in_window


def _stages_for(staff, start, end):
    """One read, two answers: the period's stages and the open backlog.

    A stage counts as this PERIOD'S if it was completed in it, or is still open
    having started in it. `started_at`/`completed_at` are datetimes and the
    period is a pair of boutique-local dates, so that test is made on the local
    date -- the same rule attendance uses to decide which day a shift is on. The
    database narrows to a UTC range a day wider than the period first, because
    without it this loaded every stage the person had ever been assigned and the
    cost of asking about one week grew with their whole tenure. A day of slack
    each side beats any real zone offset (the widest is 14 hours), so the exact
    check below still sees every candidate it would have seen before.

    The BACKLOG is every unsettled stage regardless of date, which is why the
    filter carries an un-windowed third clause. `reliability_metrics` needs it
    and the period metrics need the windowed set; asking separately cost two
    queries per staff member on a team dashboard, and django-tenants puts a
    SET search_path in front of each one, so a saved query saves two round trips.
    """
    lo = datetime.combine(start - timedelta(days=1), time.min, tzinfo=utc)
    hi = datetime.combine(end + timedelta(days=1), time.max, tzinfo=utc)
    rows, open_stages = [], []
    for stage in OrderStage.objects.filter(
        Q(completed_at__range=(lo, hi))
        | Q(completed_at__isnull=True, started_at__range=(lo, hi))
        | ~Q(status__in=SETTLED),
        assigned_to=staff,
    ):
        if stage.status not in SETTLED:
            open_stages.append(stage)
        moment = stage.completed_at or stage.started_at
        if moment is None:
            continue
        day = to_local(moment).date()
        if start <= day <= end:
            rows.append(stage)
    return rows, open_stages


def productivity_metrics(staff, start, end, stages=None):
    """Work touched in the period, and how much of it finished. Source: OrderStage.

    `in_period` counts stages this person STARTED OR COMPLETED inside the window,
    which is not the same as work they were given. `assign_stage` writes only
    `assigned_to` and no timestamp, so a stage handed over and never begun has no
    date to place it in any period and cannot appear here. That is why this key
    is named for what it measures; the count of work outstanding right now lives
    in `reliability_metrics`, which needs no window to be truthful.
    """
    stages = _stages_in_window(staff, start, end) if stages is None else stages
    if not stages:
        return {
            'in_period': _metric(0),
            'completed': _metric(0),
            'completion_rate': _unavailable('No work was worked on in this period.'),
            'performed_by_them': _metric(0),
        }
    completed = [s for s in stages if s.status == 'COMPLETED']
    # A SKIPPED stage was called off, not failed -- an optional maggam_work the
    # customer dropped is not an incompletion. It used to sit in the denominator
    # here while `reliability_metrics` counted it as settled, so the same stage
    # made completion look worse and consistency look fine. Both now treat it
    # the same way: out of the reckoning.
    counted = [s for s in stages if s.status != 'SKIPPED']
    return {
        'in_period': _metric(len(stages)),
        'completed': _metric(len(completed)),
        'completion_rate': _ratio(len(completed), len(counted)),
        # Assigned to them AND done by them. The gap between this and
        # `completed` is work somebody else finished on their behalf.
        'performed_by_them': _metric(
            sum(1 for s in completed if s.performed_by_id == staff.id)),
    }


def timeliness_metrics(staff, start, end, stages=None):
    """On time against the boutique's own SLA. Source: OrderStage.sla_hours."""
    stages = _stages_in_window(staff, start, end) if stages is None else stages
    # A stage with no SLA on it made no promise, so it can be neither kept nor
    # broken and is left out of the denominator entirely. Treating a missing
    # sla_hours as zero -- which this did -- made every such stage overdue the
    # instant it was started, manufacturing lateness out of an absent target and
    # putting it on someone's review. `reliability_metrics` below has always
    # skipped these; the two now agree.
    finished = [s for s in stages
                if s.status == 'COMPLETED' and s.started_at and s.completed_at
                and s.sla_hours]
    if not finished:
        return {
            'measured': _metric(0),
            'on_time': _metric(0),
            'overdue': _metric(0),
            'on_time_rate': _unavailable(
                'No completed work with an SLA and both timestamps in this period.'),
            'average_delay_hours': _unavailable(
                'No completed work with an SLA and both timestamps in this period.'),
        }

    on_time, overdue, delays = 0, 0, []
    for stage in finished:
        allowed = timedelta(hours=stage.sla_hours)
        elapsed = stage.completed_at - stage.started_at
        if elapsed <= allowed:
            on_time += 1
        else:
            overdue += 1
            delays.append((elapsed - allowed).total_seconds() / 3600)
    return {
        'measured': _metric(len(finished)),
        'on_time': _metric(on_time),
        'overdue': _metric(overdue),
        'on_time_rate': _ratio(on_time, len(finished)),
        # Averaged over the LATE ones only. Folding the on-time work in would
        # dilute "how late, when late" into a number that answers nothing.
        'average_delay_hours': (_metric(round(sum(delays) / len(delays), 2))
                                if delays else _metric(0)),
    }


def quality_metrics(staff, start, end):
    """Quality, from whatever QC records exist. Never invented.

    See the module docstring: QCRecords CAN be written (via /api/production/qc/)
    but no screen drives that endpoint, so the table is usually empty. This reads
    the table either way -- with records it reports real figures, with none it
    returns the ratios as unavailable with the reason attached.
    """
    from apps.production.models import QCRecord

    period = dict(created_at__date__gte=start, created_at__date__lte=end)
    # Two different facts, kept apart. `inspected` is how much checking this
    # person DID; the pass and rework rates are about work they were checked ON.
    # Merged with an OR -- which this used to do -- a QC Master who inspects
    # four of somebody else's garments and rejects three reports a 75% rework
    # rate against their own name, for defects they found rather than made.
    #
    # Kept apart but fetched TOGETHER: four conditional counts in one aggregate
    # rather than a query apiece, because this runs once per staff member on a
    # team dashboard and django-tenants adds a SET search_path to each one.
    counts = QCRecord.objects.filter(**period).aggregate(
        inspected=Count('id', filter=Q(inspector=staff)),
        checked=Count('id', filter=Q(task__assigned_to=staff)),
        passed=Count('id', filter=Q(task__assigned_to=staff, status='PASSED')),
        rework=Count('id', filter=Q(task__assigned_to=staff,
                                    status='REWORK_REQUIRED')),
    )
    inspected = counts['inspected']
    total = counts['checked']
    if not total:
        reason = ('No quality checks were recorded for this person in this '
                  'period. Nothing in the product creates QC records today.')
        return {
            'inspected': _metric(inspected),
            'checked': _metric(0),
            'passed': _unavailable(reason),
            'rework': _unavailable(reason),
            'pass_rate': _unavailable(reason),
            'rework_rate': _unavailable(reason),
        }

    passed = counts['passed']
    rework = counts['rework']
    return {
        'inspected': _metric(inspected),
        'checked': _metric(total),
        'passed': _metric(passed),
        'rework': _metric(rework),
        'pass_rate': _ratio(passed, total),
        'rework_rate': _ratio(rework, total),
    }


def reliability_metrics(staff, start, end, stages=None, attendance=None,
                        open_stages=None):
    """Consistency, derived only from what is measurable.

    Two facts, both from data that exists: how much assigned work is still
    unfinished, and whether attendance was left open. Nothing subjective is
    inferred here -- judgement about reliability belongs in the review's rating,
    written by a person.

    OUTSTANDING WORK IS COUNTED WITHOUT A WINDOW, deliberately. "What is still
    on this person's bench" is a fact about now, not about a date range, and
    windowing it hid the two cases it most needed to catch: a stage assigned and
    never begun (no timestamp, so it belongs to no period) and a stage started
    months ago and still open (its timestamp falls outside the window). Both used
    to report zero outstanding for the person sitting on the oldest job in the
    boutique. The period-scoped figures stay in `productivity_metrics`.
    """
    if stages is None:
        stages, open_stages = _stages_for(staff, start, end)
    elif open_stages is None:
        _ignored, open_stages = _stages_for(staff, start, end)
    # Overdue is judged at the end of the period being asked about, not at the
    # wall clock: re-opening a closed September in December must not keep
    # inventing fresh lateness, and a finalised snapshot must not depend on the
    # minute Finalise was pressed.
    asof = min(timezone.now(),
               datetime.combine(end, time.max, tzinfo=utc) + timedelta(days=1))
    overdue_open = 0
    for stage in open_stages:
        if stage.started_at and stage.sla_hours:
            if asof - stage.started_at > timedelta(hours=stage.sla_hours):
                overdue_open += 1
    if attendance is None:
        attendance = attendance_metrics(staff, start, end)
    # Same basis as completion_rate: a called-off stage is neither a success
    # nor a failure, so it leaves the denominator rather than counting as done.
    counted = [s for s in stages if s.status != 'SKIPPED']
    finished = [s for s in counted if s.status in SETTLED]
    return {
        'outstanding_assignments': _metric(len(open_stages)),
        'overdue_open_assignments': _metric(overdue_open),
        'unclosed_attendance_sessions': attendance['open_sessions'],
        'completion_consistency': _ratio(len(finished), len(counted)),
    }


def staff_metrics(staff, start, end, *, profile=None):
    """Everything measurable about one person's work in one period.

    The window is narrowed to the employment first, so somebody who joined
    midway is measured on the days they were actually here.
    """
    if profile is None:
        profile = StaffProfile.objects.filter(staff=staff).first()
    first, last = effective_window(profile, start, end)
    if first > last:
        empty = _unavailable('Not employed during this period.')
        # The window as ASKED FOR, not the inverted one the narrowing produced.
        # Reporting first > last (a Dec joiner queried for September gave
        # 2026-12-01 to 2026-09-30) describes a period that cannot exist.
        return {
            'staff': staff.id, 'staff_name': staff.name, 'role': staff.role,
            'period_start': start, 'period_end': end, 'employed_in_period': False,
            'attendance': {'worked_hours': empty, 'days_attended': empty,
                           'average_hours_per_day': empty, 'worked_minutes': empty,
                           'open_sessions': empty},
            'productivity': {'in_period': empty, 'completed': empty,
                             'completion_rate': empty, 'performed_by_them': empty},
            'timeliness': {'measured': empty, 'on_time': empty, 'overdue': empty,
                           'on_time_rate': empty, 'average_delay_hours': empty},
            'quality': {'inspected': empty, 'checked': empty, 'passed': empty,
                        'rework': empty, 'pass_rate': empty, 'rework_rate': empty},
            'reliability': {'outstanding_assignments': empty,
                            'overdue_open_assignments': empty,
                            'unclosed_attendance_sessions': empty,
                            'completion_consistency': empty},
        }

    # Read once, shared by the four groups that need them. Each of these used
    # to fetch its own copy, so a single staff member cost three identical
    # stage queries and two identical attendance queries.
    stages, open_stages = _stages_for(staff, first, last)
    attendance = attendance_metrics(staff, first, last)
    return {
        'staff': staff.id,
        'staff_name': staff.name,
        'role': staff.role,
        'period_start': first,
        'period_end': last,
        'employed_in_period': True,
        'attendance': attendance,
        'productivity': productivity_metrics(staff, first, last, stages),
        'timeliness': timeliness_metrics(staff, first, last, stages),
        'quality': quality_metrics(staff, first, last),
        'reliability': reliability_metrics(staff, first, last, stages, attendance,
                                           open_stages),
    }


#: What each role is actually measured on. Not one generic set pretending a
#: presser and a designer do the same job: a QC Master's inspections mean
#: something a Cutting Master's do not, and a set that fits everybody fits
#: nobody. Roles absent here fall back to DEFAULT_KPIS.
ROLE_KPIS = {
    'Tailor': ('attendance.worked_hours', 'productivity.completed',
               'productivity.completion_rate', 'timeliness.on_time_rate',
               'quality.rework_rate'),
    # A supervisor's five figures. `outstanding_assignments` is the one that
    # actually answers "who is sitting on work", and it is window-free for that
    # reason -- the windowed version reported 0 for the person holding the
    # oldest job in the boutique.
    'Master': ('attendance.worked_hours', 'productivity.in_period',
               'productivity.completion_rate', 'timeliness.on_time_rate',
               'reliability.outstanding_assignments'),
    'Cutting Master': ('attendance.worked_hours', 'productivity.completed',
                       'timeliness.on_time_rate', 'quality.rework_rate'),
    'Measurement Master': ('attendance.worked_hours', 'productivity.completed',
                           'timeliness.on_time_rate'),
    'Pattern Master': ('attendance.worked_hours', 'productivity.completed',
                       'timeliness.on_time_rate', 'quality.rework_rate'),
    'Maggam Master': ('attendance.worked_hours', 'productivity.completed',
                      'productivity.completion_rate', 'quality.rework_rate'),
    'Finishing Master': ('attendance.worked_hours', 'productivity.completed',
                         'timeliness.on_time_rate', 'quality.rework_rate'),
    'Pressing Staff': ('attendance.worked_hours', 'productivity.completed',
                       'timeliness.on_time_rate'),
    'QC Master': ('attendance.worked_hours', 'quality.inspected',
                  'quality.pass_rate', 'timeliness.on_time_rate'),
}

DEFAULT_KPIS = ('attendance.worked_hours', 'productivity.completed',
                'productivity.completion_rate', 'timeliness.on_time_rate')


def kpis_for_role(role):
    return ROLE_KPIS.get(role, DEFAULT_KPIS)


def headline_kpis(metrics):
    """The handful of figures that matter for this person's role.

    Reads the same metric dictionary everything else does, so a headline can
    never disagree with the detail underneath it.
    """
    out = []
    for path in kpis_for_role(metrics.get('role')):
        group, name = path.split('.')
        metric = (metrics.get(group) or {}).get(name)
        if metric is not None:
            out.append({'key': path, 'group': group, 'name': name, **metric})
    return out
