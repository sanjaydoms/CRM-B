"""Advances: what the boutique lent, and what payroll has taken back.

THE INVARIANT
=============
An advance is recovered exactly once per payroll, never beyond what is still
outstanding on it, never beyond what the week has left after the deposit, and
always traceably to the payroll that took it.

DEDUCTION ORDER
===============
Deposit first, advance second. Not a preference -- the deposit is a standing
term of employment and the advance is a loan taken against pay, so the loan
draws on what the term leaves. `recovery_for` therefore receives NOT the gross
but what deposit recovery left of it, and can never see money the deposit has
already claimed. The order is fixed here and nowhere else.

WHICH ADVANCE
=============
Oldest outstanding first, one per week. A week's recovery is applied to the
single oldest advance that still has anything owing on it, and stops there --
even when that advance's remainder is smaller than what the week could bear.
Finishing one obligation before touching the next keeps "which loan did this
rupee repay" a question with one answer, which is the whole reason advances are
separate rows rather than one running balance.

WHERE MONEY MOVES
=================
Only in `issue`, `cancel` and `record_recovery`, and the last of those only
from payroll approval. Drafting reads and calculates; it writes nothing here.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction

from crm_api.models import Tailor

from .models import StaffAdvance, StaffLedgerEntry

TWO_PLACES = Decimal('0.01')
ZERO = Decimal('0.00')


def _money(value):
    return (value or ZERO).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


class AdvanceError(ValueError):
    """This advance action cannot happen, and nothing has been written."""


def _sum(advance, entry_type):
    total = ZERO
    for entry in StaffLedgerEntry.objects.filter(advance=advance, entry_type=entry_type):
        total += entry.amount
    return _money(total)


def outstanding_for(advance):
    """What is still owed on one advance, from its ledger rows alone.

    issued - recovered - cancelled, floored at zero. A cancelled advance
    reverses its own issue, so its outstanding is zero by arithmetic rather than
    by a status check.
    """
    E = StaffLedgerEntry.EntryType
    owed = (_sum(advance, E.ADVANCE_ISSUED)
            - _sum(advance, E.ADVANCE_RECOVERY)
            - _sum(advance, E.ADVANCE_CANCELLED))
    return owed if owed > ZERO else ZERO


def recovered_for(advance):
    return _sum(advance, StaffLedgerEntry.EntryType.ADVANCE_RECOVERY)


def advance_state(advance):
    return {
        'issued': _money(advance.amount),
        'recovered': recovered_for(advance),
        'outstanding': outstanding_for(advance),
        'cancelled': advance.is_cancelled,
    }


def outstanding_advances(staff):
    """This person's advances that still have anything owing, oldest first."""
    if staff is None:
        return []
    result = []
    for advance in StaffAdvance.objects.filter(
            staff=staff, status=StaffAdvance.Status.ACTIVE
    ).order_by('issued_on', 'created_at', 'pk'):
        owed = outstanding_for(advance)
        if owed > ZERO:
            result.append((advance, owed))
    return result


def total_outstanding(staff):
    return _money(sum((owed for _, owed in outstanding_advances(staff)), ZERO))


def recovery_for(staff, available):
    """What this week's payroll should take back, and from which advance.

    `available` is what the deposit left of the gross -- see the module
    docstring. None means the payroll is unpayable; nothing is recovered from a
    week that cannot itself be approved.

    Three clamps, in order:
      1. only the oldest advance with money owing
      2. never more than is owed on it
      3. never more than the week has left after the deposit
    The shortfall between what the rule scheduled and what was collectable is
    returned rather than absorbed, for the same reason as the deposit: a missed
    500 is a fact the record must keep.
    """
    nothing = {'advance': None, 'scheduled': ZERO, 'recovered': ZERO,
               'unrecovered': ZERO, 'balance_before': ZERO, 'balance_after': ZERO}
    if staff is None:
        return nothing
    queue = outstanding_advances(staff)
    if not queue:
        return nothing

    # The oldest advance that is actually BEING repaid. A weekly rule of zero
    # means "not yet" -- an advance parked while the person gets on their feet
    # -- and parking the oldest one must not freeze recovery of every newer
    # one behind it. Still oldest-first among those with a rule.
    scheduled_queue = [(a, o) for a, o in queue if _money(a.weekly_recovery) > ZERO]
    if not scheduled_queue:
        advance, owed = queue[0]
        return {**nothing, 'advance': advance,
                'balance_before': owed, 'balance_after': owed}
    advance, owed = scheduled_queue[0]
    weekly = _money(advance.weekly_recovery)

    due = min(weekly, owed)
    payable = ZERO if available is None else _money(available)
    actual = min(due, payable if payable > ZERO else ZERO)
    return {
        'advance': advance,
        'scheduled': due,
        'recovered': actual,
        'unrecovered': due - actual,
        'balance_before': owed,
        'balance_after': owed - actual,
    }


@transaction.atomic
def issue(staff, amount, *, user, issued_on, reason='', weekly_recovery=ZERO):
    """Lend money to a staff member and write it down.

    The advance row and its ADVANCE_ISSUED ledger row are one transaction: an
    advance with no ledger entry would have no balance, and a ledger entry with
    no advance would have no terms.
    """
    amount = _money(amount)
    if amount <= ZERO:
        raise AdvanceError('An advance must be a positive amount.')
    weekly = _money(weekly_recovery)
    if weekly < ZERO:
        raise AdvanceError('Weekly recovery cannot be negative.')
    if issued_on is None:
        raise AdvanceError('An advance needs the date it was given.')

    advance = StaffAdvance.objects.create(
        staff=staff, staff_name_snapshot=staff.name,
        amount=amount, weekly_recovery=weekly, issued_on=issued_on,
        reason=(reason or '').strip(), created_by=user)
    StaffLedgerEntry.objects.create(
        staff=staff, staff_name_snapshot=staff.name,
        entry_type=StaffLedgerEntry.EntryType.ADVANCE_ISSUED,
        amount=amount, balance_before=ZERO, balance_after=amount,
        advance=advance, note=reason or 'Advance issued', recorded_by=user)
    return advance


@transaction.atomic
def cancel(advance, *, user, reason=''):
    """Reverse an advance entered in error. Only before anything is recovered.

    An offset row, not a deletion. The wrong entry and its correction both
    stay in the ledger, so the history can be read as it happened. Once a
    payroll has recovered against the advance, cancelling would orphan that
    recovery -- correcting that is a settlement question for a later phase.
    """
    reason = (reason or '').strip()
    if not reason:
        raise AdvanceError('Give a reason for cancelling this advance.')
    # Serialise with payroll approval on the same person, then re-read the
    # advance under that lock. Without both, a cancel and an approval could
    # interleave: the approval writes a recovery against an advance the cancel
    # is reversing in the same instant, and a second cancel tap could write a
    # second reversal. The guards below must see committed truth.
    Tailor.objects.select_for_update().filter(pk=advance.staff_id).first()
    advance = StaffAdvance.objects.select_for_update().get(pk=advance.pk)
    if advance.is_cancelled:
        raise AdvanceError('This advance is already cancelled.')
    if recovered_for(advance) > ZERO:
        raise AdvanceError(
            'This advance has already been partly recovered through payroll '
            'and cannot be cancelled.')

    from django.utils import timezone
    owed = outstanding_for(advance)
    StaffLedgerEntry.objects.create(
        staff=advance.staff, staff_name_snapshot=advance.staff_name_snapshot,
        entry_type=StaffLedgerEntry.EntryType.ADVANCE_CANCELLED,
        amount=owed, balance_before=owed, balance_after=ZERO,
        advance=advance, note=reason, recorded_by=user)
    advance.status = StaffAdvance.Status.CANCELLED
    advance.cancelled_at = timezone.now()
    advance.cancelled_by = user
    advance.cancel_reason = reason
    advance.save(update_fields=['status', 'cancelled_at', 'cancelled_by',
                                'cancel_reason'])
    return advance


def set_weekly_recovery(advance, weekly, *, user):
    """Change the repayment rule for future weeks. Past weeks are untouched.

    Nothing here rewrites a payroll record: every past recovery is a snapshot
    on its own record and a row in the ledger, and both keep the figure that
    was actually taken.
    """
    weekly = _money(weekly)
    if weekly < ZERO:
        raise AdvanceError('Weekly recovery cannot be negative.')
    if advance.is_cancelled:
        raise AdvanceError('A cancelled advance has no recovery to change.')
    advance.weekly_recovery = weekly
    advance.save(update_fields=['weekly_recovery'])
    return advance


def record_recovery(record, *, user):
    """Take this payroll's advance recovery, once.

    Called only from payroll approval, inside its transaction. The person is
    locked (the same lock deposits.record_recovery takes, so both recoveries for
    one staff member serialise against any other week's approval), the
    outstanding balance is re-read under that lock, and an amount the balance
    no longer supports is refused rather than trimmed -- a payroll record that
    says 500 above a ledger row that says 300 is worse than a failed approval.
    """
    if record.advance_recovered <= ZERO or record.staff is None:
        return None
    advance = record.advance_recovered_from
    if advance is None:
        raise AdvanceError(
            f"{record.staff_name_snapshot}'s payroll records an advance recovery "
            f"but not which advance. Generate it again.")

    Tailor.objects.select_for_update().filter(pk=record.staff_id).first()
    # Under the lock, is it still an advance? A cancel that committed a moment
    # ago has already reversed it, and the arithmetic below would still see the
    # ISSUED row. Status is checked by name, not inferred.
    advance = StaffAdvance.objects.select_for_update().get(pk=advance.pk)
    if advance.is_cancelled:
        raise AdvanceError(
            f"{record.staff_name_snapshot}'s advance was cancelled after this "
            f"payroll was drafted. Generate it again.")

    owed = outstanding_for(advance)
    amount = _money(record.advance_recovered)
    if amount > owed:
        raise AdvanceError(
            f'Recovery of {amount} exceeds the {owed} still owed on '
            f"{record.staff_name_snapshot}'s advance.")
    if owed <= ZERO:
        return None

    return StaffLedgerEntry.objects.create(
        staff=record.staff, staff_name_snapshot=record.staff_name_snapshot,
        entry_type=StaffLedgerEntry.EntryType.ADVANCE_RECOVERY,
        amount=amount, balance_before=owed, balance_after=owed - amount,
        payroll_record=record, advance=advance,
        note=f'Recovered from payroll week of {record.period.period_start}',
        recorded_by=user)


def ledger_for(advance):
    return StaffLedgerEntry.objects.filter(advance=advance).order_by('created_at')
