"""The one place attendance minutes become money.

Nothing else multiplies a rate by an hour -- not a serializer, not a viewset,
not React. `domains/orders/pricing.py` sets that precedent for customer money
and its docstring explains what happened when a second implementation existed:
the two drifted and the wrong one printed on an invoice. Staff money gets the
same treatment from the start.

ROUNDING
========
Decimal throughout, quantized to two places with ROUND_HALF_UP, ONCE, at the
end. The rule deliberately matches the order pricing module -- a boutique should
not have two rounding behaviours -- but is restated here rather than imported,
because payroll must not depend on the customer-billing domain. `to_money` in
that module also swallows unparseable input to 0.00, which is right for a price
typed into a form and catastrophic for a wage: a missing rate must stop payroll,
not pay nothing.

Rounding once matters. 25 minutes at Rs.100/hour is 41.6666...; rounding hours
to 0.42 first and multiplying gives 42.00, and the error compounds with every
session. So minutes stay integers, the division happens inside the Decimal
expression, and only the final rupee figure is quantized.

WHAT IS PAYABLE
===============
Completed AttendanceSession rows and nothing else. Not login duration, not
OrderStage.duration_seconds (wall-clock, runs through nights), not
ProductionTask.actual_hours (never written). An open session pays nothing and is
reported rather than guessed at.
"""

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.staff.attendance import week_start
from apps.staff.models import AttendanceSession, StaffProfile

from . import advances, deposits
from .models import PayrollPeriod, PayrollRecord

#: Two places, half up. The same money shape the rest of the product uses.
TWO_PLACES = Decimal('0.01')
MINUTES_PER_HOUR = Decimal('60')


class PayrollError(ValueError):
    """This payroll action cannot happen, and nothing has been written.

    ValueError so the view layer's existing 400 handling applies; the message is
    the point, because every one of these is something the owner must go and fix
    rather than retry.
    """


def gross_for(minutes, rate):
    """Minutes at a rate, as rupees. None rate means unpayable, not free.

    Returning None rather than Decimal('0.00') is the whole safety property: a
    zero would flow into a total, get approved, and pay somebody nothing for a
    week they worked. None cannot be added up by accident.
    """
    if rate is None:
        return None
    # MULTIPLY BEFORE DIVIDING. The order is the whole correctness of this line.
    #
    # `minutes / 60` first looks equivalent and is not: Decimal division is
    # rounded to the context precision (28 significant digits), so for any
    # minutes not divisible by 3 the quotient is already approximate before the
    # rate is applied. The approximation lands a hair BELOW an exact half-paise
    # tie, so the final ROUND_HALF_UP rounds down where exact arithmetic rounds
    # up -- 242 minutes at 18.75 is exactly 75.625 and came out as 75.62.
    # Always downwards, so always against the person being paid.
    #
    # An integer times a two-place Decimal is EXACT, so multiplying first leaves
    # the single trailing division as the only inexact step, and the quantize
    # below is then genuinely the only rounding -- which is what the module
    # docstring promises. Checked by exhaustive scan against Fraction
    # arithmetic: division-first is wrong in 1,532 of 283,800 minute/rate
    # combinations, multiplication-first in none of them.
    return (Decimal(int(minutes)) * Decimal(rate) / MINUTES_PER_HOUR).quantize(
        TWO_PLACES, rounding=ROUND_HALF_UP)


def period_bounds(day):
    """The Monday-to-Sunday week containing `day`, boutique-local.

    Delegates to the attendance module rather than restating the rule: the
    timesheet and the payslip must cover exactly the same seven days, and two
    definitions of "the week" is how they would stop doing so.
    """
    start = week_start(day)
    return start, start + timedelta(days=6)


def _payable_window(profile, start, end):
    """The days of this period the person was actually employed for.

    Attendance recorded before someone joined or after they left is real -- it
    happened, and it stays in the timesheet -- but it is not this employment's
    to pay. Narrowing the window is how a midweek joiner gets paid from
    Wednesday without anyone editing their attendance.
    """
    first = start
    last = end
    if profile.joined_at and profile.joined_at > first:
        first = profile.joined_at
    if profile.exit_date and profile.exit_date < last:
        last = profile.exit_date
    return first, last


def _overlaps(sessions):
    """Whether any two completed sessions cover the same instant.

    The database stops a second OPEN session, so this cannot arise from normal
    check-ins. It can arise from owner corrections: move one session's check-out
    past the next session's check-in and the same hour now sits in two rows.
    Summing them would pay it twice.

    Reported rather than resolved. Picking a winner silently -- dropping the
    shorter, truncating the earlier -- would be this module inventing an
    attendance record, which is exactly what it must never do.
    """
    ordered = sorted(sessions, key=lambda s: s.check_in)
    for earlier, later in zip(ordered, ordered[1:]):
        if earlier.check_out and earlier.check_out > later.check_in:
            return True
    return False


def _breakdown(sessions):
    """The per-session evidence behind the total, frozen as plain JSON.

    Not a copy of the attendance table -- it holds the id and the values used,
    so an approved record can still show its working after the live session has
    been corrected. Datetimes are isoformat strings because a JSONField cannot
    hold a datetime and because these must not shift meaning later.
    """
    return [
        {
            'id': str(s.id),
            'date': s.date.isoformat(),
            'check_in': s.check_in.isoformat(),
            'check_out': s.check_out.isoformat() if s.check_out else None,
            'minutes': int(s.minutes or 0),
            'source': s.source,
            'was_corrected': s.corrected_at is not None,
        }
        for s in sorted(sessions, key=lambda s: s.check_in)
    ]


def already_paid_session_ids(staff):
    """Sessions a frozen (APPROVED or PAID) payroll has already paid for.

    Guards a real double-payment path rather than a theoretical one. A session's
    `date` is derived from its check-in, and an owner correction can move that
    check-in -- so correcting a Sunday 23:00 start to Monday 00:30 moves the
    session out of an already-approved week and into the next one. Without this,
    the next run would pay for it a second time, and the approved run cannot
    give the money back because it is frozen.

    Read from the frozen `session_breakdown` rather than by re-querying
    attendance, because the breakdown is what the approved run actually paid --
    which is the only correct definition of "already paid".
    """
    paid = set()
    # APPROVED *and* PAID. A record leaves APPROVED for PAID the moment it is
    # settled, and the first version filtered on APPROVED alone -- so paying a
    # week made every session it had paid for eligible again. Any frozen
    # status counts; the only thing that must NOT count is a draft.
    for record in PayrollRecord.objects.filter(
            staff=staff, status__in=[PayrollRecord.Status.APPROVED,
                                     PayrollRecord.Status.PAID]):
        paid.update(entry.get('id') for entry in (record.session_breakdown or []))
    paid.discard(None)
    return paid


def _calculate_for(profile, start, end):
    """Everything one person's record needs, without touching the database."""
    first, last = _payable_window(profile, start, end)

    if first > last:
        # Employment does not overlap this week at all -- joined after it
        # ended, or left before it began.
        return None

    in_window = AttendanceSession.objects.filter(
        staff=profile.staff, date__gte=first, date__lte=last)
    paid = already_paid_session_ids(profile.staff)
    completed = [s for s in in_window
                 if s.check_out is not None and str(s.id) not in paid]
    open_count = sum(1 for s in in_window if s.check_out is None)

    minutes = sum(int(s.minutes or 0) for s in completed)

    # Nothing happened and nothing is pending: no record. A zero-rupee row for
    # somebody who was on leave is noise in a payroll run, and this product's
    # rule from Phase 1 onwards has been not to conjure records nobody asked
    # for. A person with an OPEN session still gets a row, because the warning
    # attached to it is the reason they need to appear.
    if minutes == 0 and open_count == 0:
        return None

    rate = profile.hourly_rate
    # Zero is treated as unset, not as "pays nothing". A rate of 0.00 is the
    # default on a profile nobody has filled in, so paying it would silently
    # produce a week of free labour for every staff member the owner had not
    # got round to configuring.
    usable_rate = rate if (rate is not None and rate > 0) else None

    gross = gross_for(minutes, usable_rate)

    # The deposit layer sits ON TOP of the Phase 4 gross calculation and does
    # not touch it: `gross_earnings` above is computed exactly as before, and
    # the recovery is then clamped against it. Nothing here can change what
    # somebody earned -- only what is taken from it.
    recovery = deposits.recovery_for(profile.staff, profile, gross)
    after_deposit = None if gross is None else gross - recovery['recovered']

    # DEDUCTION ORDER: deposit, then advance. The advance layer is handed what
    # the deposit LEFT, never the gross, so the two can never together take
    # more than the week earned. Documented in advances.py and tested; the
    # interface is not consulted about the order.
    advance = advances.recovery_for(profile.staff, after_deposit)
    net_payable = None if after_deposit is None else after_deposit - advance['recovered']

    return {
        'staff_name_snapshot': profile.staff.name,
        'staff_role_snapshot': profile.staff.role or '',
        'hourly_rate_snapshot': usable_rate,
        'worked_minutes': minutes,
        'regular_minutes': minutes,
        'gross_earnings': gross,
        'open_session_count': open_count,
        'has_overlap': _overlaps(completed),
        'session_breakdown': _breakdown(completed),
        'deposit_scheduled': recovery['scheduled'],
        'deposit_recovered': recovery['recovered'],
        'deposit_unrecovered': recovery['unrecovered'],
        'deposit_balance_before': recovery['balance_before'],
        'deposit_balance_after': recovery['balance_after'],
        'net_before_other_deductions': after_deposit,
        'advance_recovered_from': advance['advance'],
        'advance_scheduled': advance['scheduled'],
        'advance_recovered': advance['recovered'],
        'advance_unrecovered': advance['unrecovered'],
        'advance_balance_before': advance['balance_before'],
        'advance_balance_after': advance['balance_after'],
        'net_payable': net_payable,
    }


def eligible_profiles():
    """Staff who can appear in a payroll run at all.

    An employment profile is the entry condition, which is what keeps payroll
    aligned with Phase 1: a Tailor without one is a perfectly normal staff
    member whose employment has not been set up, and inventing pay for them
    would be the same mistake as inventing the profile.
    """
    return StaffProfile.objects.select_related('staff').all()


@transaction.atomic
def generate(day, *, user):
    """Build or rebuild the draft payroll for the week containing `day`.

    Idempotent by construction: the period is unique on its Monday and each
    record is unique on (period, staff), so pressing Generate three times
    produces one period and one row per person. The third press recalculates
    rather than duplicating, which is also how a corrected attendance record
    reaches a draft payroll.

    An APPROVED period is refused outright. Recalculating one would rewrite a
    number somebody has already signed off, which is the single thing approval
    exists to prevent.
    """
    start, end = period_bounds(day)

    try:
        period, _ = PayrollPeriod.objects.get_or_create(
            period_start=start,
            defaults={'period_end': end, 'created_by': user},
        )
    except IntegrityError:
        raise PayrollError('That payroll week is already being generated.')

    # Lock it before deciding anything: two tabs pressing Generate and Approve
    # together must not have Generate rewrite a period Approve has just locked.
    period = PayrollPeriod.objects.select_for_update().get(pk=period.pk)
    if period.is_approved:
        raise PayrollError(
            f'Payroll for {start} to {end} has been approved and cannot be '
            f'regenerated. Approved payroll is a record, not a draft.')

    seen = []
    for profile in eligible_profiles():
        values = _calculate_for(profile, start, end)
        if values is None:
            continue
        record, _ = PayrollRecord.objects.update_or_create(
            period=period, staff=profile.staff,
            defaults={**values, 'status': PayrollRecord.Status.DRAFT},
        )
        seen.append(record.pk)

    # Someone whose attendance was removed, or who left before the week began,
    # should not linger from an earlier run. Only ever touches DRAFT rows.
    PayrollRecord.objects.filter(
        period=period, status=PayrollRecord.Status.DRAFT
    ).exclude(pk__in=seen).delete()

    return period


def blocking_records(period):
    """Draft rows that cannot be signed off, and why."""
    return [r for r in period.records.all() if r.blocks_approval]


@transaction.atomic
def approve(period, *, user):
    """Freeze a week's payroll.

    Re-read under `select_for_update` rather than trusting the instance the view
    fetched: two tabs both passed the status check a moment ago, and the lock is
    what makes the second one lose. Without it both would write APPROVED and
    both would report success.

    Deliberately does NOT recalculate. The draft the owner reviewed is the thing
    they are approving; recomputing at this moment could quietly change the
    figure between the confirmation dialog and the record, which is the one
    place a payroll system must never surprise anybody.
    """
    locked = PayrollPeriod.objects.select_for_update().get(pk=period.pk)
    if locked.is_approved:
        raise PayrollError('This payroll week has already been approved.')

    blockers = blocking_records(locked)
    if blockers:
        names = ', '.join(sorted(r.staff_name_snapshot for r in blockers))
        raise PayrollError(
            f'Payroll cannot be approved yet: {names} '
            f'{"has" if len(blockers) == 1 else "have"} an unresolved problem. '
            f'Set a missing hourly rate, or fix overlapping attendance, and '
            f'generate again.')

    if not locked.records.exists():
        raise PayrollError(
            'There is nothing to approve for this week -- no staff member has '
            'any completed attendance.')

    # The draft may be stale -- another week could have been approved since it
    # was calculated, reducing what is still owed. Refuse rather than quietly
    # collect a figure the owner reviewed but the obligation no longer supports.
    # Refusing keeps the promise that approving means approving WHAT WAS SHOWN;
    # silently reducing it would break that promise in the direction of money.
    for record in locked.records.all():
        # A draft can outlive the person on it: the roster row is deleted, the
        # CASCADE takes their StaffProfile, and the draft row keeps its figures
        # with staff=NULL. Approving that would freeze a recovery no ledger row
        # can be written for. Refuse; regenerating drops the orphan.
        if record.staff_id is None and (
                record.deposit_recovered > 0 or record.advance_recovered > 0):
            raise PayrollError(
                f"{record.staff_name_snapshot} is no longer on the roster but "
                f"this draft still deducts from them. Generate it again.")
        if record.deposit_recovered > 0:
            outstanding = deposits.deposit_state(record.staff)['remaining']
            if record.deposit_recovered > outstanding:
                raise PayrollError(
                    f"{record.staff_name_snapshot}'s security deposit has changed "
                    f"since this payroll was drafted. Generate it again so the "
                    f"recovery matches what is still owed.")
        if record.advance_recovered > 0:
            advance = record.advance_recovered_from
            if advance is not None and advance.is_cancelled:
                raise PayrollError(
                    f"{record.staff_name_snapshot}'s advance was cancelled after "
                    f"this payroll was drafted. Generate it again.")
            owed = advances.outstanding_for(advance) if advance else Decimal('0.00')
            if record.advance_recovered > owed:
                raise PayrollError(
                    f"{record.staff_name_snapshot}'s advance has changed since "
                    f"this payroll was drafted. Generate it again so the "
                    f"recovery matches what is still owed.")

    now = timezone.now()
    # Everything below runs inside the approval transaction; a refusal raised
    # by either recovery (the person-level lock re-checks the live balance)
    # rolls the whole approval back. Re-raised as PayrollError so the view
    # answers 409 rather than a 500 -- the caller lost a race, not the plot.
    try:
        _freeze_records(locked, user, now)
    except ValueError as exc:
        raise PayrollError(str(exc))

    locked.status = PayrollPeriod.Status.APPROVED
    locked.approved_at = now
    locked.approved_by = user
    locked.save(update_fields=['status', 'approved_at', 'approved_by'])
    return locked


def _freeze_records(locked, user, now):
    """Stamp every record and take both recoveries. Called only from approve()."""
    # The ledger is written HERE, inside the approval transaction, and nowhere
    # else. Payroll approved without its recovery, or a recovery taken against a
    # payroll still in draft, are both states this ordering makes unreachable.
    for record in locked.records.all():
        record.status = PayrollRecord.Status.APPROVED
        record.approved_at = now
        record.approved_by = user
        entry = deposits.record_recovery(record, user=user)
        fields = ['status', 'approved_at', 'approved_by']
        if entry is not None:
            # The draft's balances were calculated when it was drafted, which
            # may have been before another week was approved. The RECOVERY is
            # the figure the owner reviewed and is left alone; the balances
            # either side of it are refreshed from the ledger row that actually
            # moved the money, so an approved record cannot state an obligation
            # that was never true.
            record.deposit_balance_before = entry.balance_before
            record.deposit_balance_after = entry.balance_after
            fields += ['deposit_balance_before', 'deposit_balance_after']
        # Same transaction, same person-level lock (taken inside the deposit
        # step and held). Approval, deposit recovery and advance recovery
        # commit together or not at all.
        advance_entry = advances.record_recovery(record, user=user)
        if advance_entry is not None:
            record.advance_balance_before = advance_entry.balance_before
            record.advance_balance_after = advance_entry.balance_after
            fields += ['advance_balance_before', 'advance_balance_after']
        record.save(update_fields=fields)


def period_totals(period):
    """The figures the confirmation dialog and the list header show."""
    records = list(period.records.all())
    zero = Decimal('0.00')
    return {
        'staff_count': len(records),
        'total_minutes': sum(r.worked_minutes for r in records),
        'total_gross': sum((r.gross_earnings or zero for r in records), zero),
        'total_deposit_recovered': sum((r.deposit_recovered for r in records), zero),
        'total_deposit_unrecovered': sum((r.deposit_unrecovered for r in records), zero),
        'total_net': sum((r.net_before_other_deductions or zero for r in records),
                         zero),
        'total_advance_recovered': sum((r.advance_recovered for r in records), zero),
        'total_advance_unrecovered': sum((r.advance_unrecovered for r in records), zero),
        'total_net_payable': sum((r.net_payable or zero for r in records), zero),
        'paid_count': sum(1 for r in records if r.is_paid),
        'blocked_count': sum(1 for r in records if r.blocks_approval),
        'open_session_count': sum(r.open_session_count for r in records),
    }
