"""The security deposit: what was agreed, what has been recovered, what is left.

THE INVARIANT
=============
A rupee can be recovered from a staff member's deposit exactly once, can never
exceed the obligation outstanding, can never make wages negative, and can always
be traced to the approved payroll that took it.

Each clause is enforced somewhere different, on purpose:

  exactly once      a partial unique index on (payroll_record) for recovery rows
  never exceeds     `recovery_for` clamps, and `approve` re-checks before writing
  never negative    the clamp to gross, plus a CheckConstraint on the net column
  always traceable  the recovery row's payroll_record FK, which cannot be null

WHERE THE MONEY MOVES
=====================
Nowhere, during generation. Drafting payroll CALCULATES a recovery and writes it
onto the draft record; it writes nothing to the ledger. The ledger entry is
created when the owner approves, in the same transaction that freezes the
payroll. That is what makes drafting safely repeatable -- pressing Generate five
times moves no money -- and what makes an approved week's recovery real.
"""

from decimal import Decimal, ROUND_HALF_UP

from crm_api.models import Tailor

from .models import PayrollRecord, StaffLedgerEntry

#: Same money shape as everything else in this app. Deposits are quantised the
#: way wages are, because they are subtracted from wages and a second rounding
#: policy would put a paise somewhere nobody could account for.
TWO_PLACES = Decimal('0.01')
ZERO = Decimal('0.00')


def _money(value):
    """Two places, half up -- named rather than left to the Decimal context.

    A bare `quantize` uses the context default, which is ROUND_HALF_EVEN, so
    this module would have rounded a half-paise the opposite way from payroll
    while claiming to share its policy. One boutique, one rounding rule.
    """
    return (value or ZERO).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def agreed_amount(staff):
    """The deposit currently agreed with this person, from the ledger.

    The NEWEST agreement row wins. Earlier ones stay exactly where they are --
    that is the history of what was agreed and when, and rewriting it would be
    the one thing a ledger exists to make impossible.
    """
    # Ordered by pk as well as time, so two agreements written in the same
    # microsecond still resolve to one deterministic answer. Unlikely, and the
    # cost of leaving it ambiguous is that two reads of the same ledger could
    # disagree about what is owed -- which is not a thing a money column may do.
    latest = StaffLedgerEntry.objects.filter(
        staff=staff, entry_type=StaffLedgerEntry.EntryType.DEPOSIT_AGREED
    ).order_by('-created_at', '-pk').first()
    return _money(latest.amount) if latest else ZERO


def recovered_amount(staff):
    """Everything ever actually taken against this person's deposit."""
    total = ZERO
    for entry in StaffLedgerEntry.objects.filter(
            staff=staff,
            entry_type=StaffLedgerEntry.EntryType.DEPOSIT_RECOVERY):
        total += entry.amount
    return _money(total)


def _no_position():
    """The answer for somebody who cannot have a deposit position."""
    return {'agreed': ZERO, 'recovered': ZERO, 'remaining': ZERO,
            'over_recovered': ZERO, 'fully_recovered': False}


def deposit_state(staff):
    """Agreed, recovered and still owed.

    `remaining` is floored at zero rather than allowed to go negative. It can
    only go below zero when an agreement is REDUCED below what has already been
    recovered -- an over-recovery, which is a refund, and refunds are a later
    phase. Flooring here means no further recovery is ever taken from someone who
    has already paid enough; `over_recovered` keeps the fact visible instead of
    swallowing it.
    """
    # A staff row that no longer exists has no position. Without this the
    # queries below filter on `staff=None`, which in SQL matches EVERY orphaned
    # ledger row -- pooling every departed staff member's history into one
    # shared balance and reporting it as an individual's.
    if staff is None:
        return _no_position()

    agreed = agreed_amount(staff)
    recovered = recovered_amount(staff)
    outstanding = agreed - recovered
    return {
        'agreed': agreed,
        'recovered': recovered,
        'remaining': outstanding if outstanding > ZERO else ZERO,
        'over_recovered': -outstanding if outstanding < ZERO else ZERO,
        'fully_recovered': agreed > ZERO and outstanding <= ZERO,
    }


def recovery_for(staff, profile, gross):
    """What this week's payroll should take, and what it will have to miss.

    Two clamps, in this order, and the order is the meaning:

      1. never more than is still owed      -- a deposit cannot over-collect
      2. never more than the week earned    -- wages cannot go negative

    The gap between what the terms scheduled and what was actually collectable
    is reported rather than absorbed. Silently reducing a 500 schedule to the 300
    a thin week could bear would leave no record that 200 was missed, and the
    difference between "the terms say 300" and "the terms say 500 and we could
    only take 300" is exactly what an owner needs months later.

    `gross` of None means the record is unpayable (no hourly rate). Nothing is
    recovered from a payroll that cannot itself be approved.
    """
    if staff is None:
        return {'scheduled': ZERO, 'recovered': ZERO, 'unrecovered': ZERO,
                'balance_before': ZERO, 'balance_after': ZERO}

    state = deposit_state(staff)
    remaining = state['remaining']

    scheduled = _money(profile.deposit_weekly)
    # Nothing is owed: no schedule, no shortfall, no ledger row. A fully
    # recovered deposit stops taking money without anybody switching it off.
    if remaining <= ZERO or scheduled <= ZERO:
        return {
            'scheduled': ZERO, 'recovered': ZERO, 'unrecovered': ZERO,
            'balance_before': remaining, 'balance_after': remaining,
        }

    # Clamp 1: the obligation. A final week takes the 250 that is left, not the
    # 500 the terms name.
    due = min(scheduled, remaining)
    # Clamp 2: the wages. This is the one that must never be skipped.
    payable = ZERO if gross is None else _money(gross)
    actual = min(due, payable)

    return {
        'scheduled': due,
        'recovered': actual,
        'unrecovered': due - actual,
        'balance_before': remaining,
        'balance_after': remaining - actual,
    }


def record_agreement(staff, amount, *, user, note=''):
    """Write down that a deposit of `amount` is now agreed with this person.

    Appends rather than edits. The previous agreement stays readable, so "why
    does this person owe 3,000 when we started at 5,000" has an answer that does
    not depend on anybody having written a note about it.
    """
    state = deposit_state(staff)
    new_total = _money(amount)
    return StaffLedgerEntry.objects.create(
        staff=staff,
        staff_name_snapshot=staff.name,
        entry_type=StaffLedgerEntry.EntryType.DEPOSIT_AGREED,
        amount=new_total,
        balance_before=state['remaining'],
        balance_after=max(new_total - state['recovered'], ZERO),
        note=note or 'Security deposit agreed',
        recorded_by=user,
    )


def record_recovery(record, *, user):
    """Take this payroll's deposit recovery, once.

    Called only from payroll approval, inside its transaction, so a week is
    never left approved-without-its-recovery or recovered-without-its-approval.

    Returns None when there is nothing to take. A zero-rupee ledger row would be
    noise in a financial history -- "we recovered nothing" is already said by the
    absence of a row and by the payroll record's own figures.

    The obligation is re-read here rather than trusted from the draft. A draft
    can be hours old, and another week may have been approved in between; the
    clamp has to be against what is owed NOW, at the moment the money moves.
    """
    if record.deposit_recovered <= ZERO or record.staff is None:
        return None

    # Lock the PERSON, not the payroll period. Two different weeks approved at
    # the same moment hold two different period locks and would otherwise both
    # read the same remaining balance and both write a recovery against it --
    # over-collecting at the boundary, where a 500 obligation pays 500 twice.
    # Serialising on the staff row is what makes "recovered exactly once"
    # survive concurrency.
    Tailor.objects.select_for_update().filter(pk=record.staff_id).first()

    state = deposit_state(record.staff)
    remaining = state['remaining']
    if remaining <= ZERO:
        return None

    amount = _money(record.deposit_recovered)
    if amount > remaining:
        # Deliberately NOT clamped. Silently taking less than the approved
        # record says would leave the payroll claiming 500 while the ledger
        # holds 300, and nothing downstream could tell which was true. approve()
        # checks this first and refuses; reaching here means that check was
        # bypassed, and the honest answer is to fail the transaction.
        raise ValueError(
            f'Recovery of {amount} exceeds the {remaining} still owed by '
            f'{record.staff_name_snapshot}.')

    return StaffLedgerEntry.objects.create(
        staff=record.staff,
        staff_name_snapshot=record.staff_name_snapshot,
        entry_type=StaffLedgerEntry.EntryType.DEPOSIT_RECOVERY,
        amount=amount,
        balance_before=remaining,
        balance_after=remaining - amount,
        payroll_record=record,
        note=f'Recovered from payroll week of {record.period.period_start}',
        recorded_by=user,
    )


def ledger_for(staff):
    """This person's financial history, oldest first."""
    return StaffLedgerEntry.objects.filter(staff=staff).order_by('created_at')
