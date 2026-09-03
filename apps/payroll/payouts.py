"""Recording that an approved payroll was paid.

Nothing here moves money. The boutique pays in cash or from its own bank and
records the fact; this module makes that record exact, single, and final.

EXACT: the amount is copied from the record's net_payable inside the same
transaction that marks it PAID. It is not accepted from the client. A payout
that differs from what was approved is a thing a later adjustment phase may
express; today it is not representable.

SINGLE: Payout is OneToOne with the payroll record. A second payout is an
IntegrityError, which is caught and reported as "already paid". The record row
is also locked for the duration, so two tabs pressing Mark Paid at once are
decided by Postgres, not by which request happened to read first.

FINAL: PAID is reached only from APPROVED and is never left. A DRAFT cannot be
paid -- there is no approved figure to pay.
"""

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Payout, PayrollRecord

ZERO = Decimal('0.00')


class PayoutError(ValueError):
    """This payout cannot be recorded, and nothing has been written."""


@transaction.atomic
def record_payout(record, *, user, method, reference='', note=''):
    """Mark one person's approved week as paid, and say how.

    Re-reads the record under `select_for_update` so the status check and the
    payout insert happen against the same locked row. Two concurrent calls
    serialise here; the second sees PAID and is refused before it can insert.
    """
    method = str(method or '').strip().upper()
    if method not in Payout.Method.values:
        raise PayoutError('Choose how this was paid: cash or bank transfer.')

    # `of=('self',)`: lock the payroll row and nothing joined to it. `staff` is
    # a nullable FK (SET_NULL so history outlives the person), which makes its
    # join an OUTER join -- and Postgres refuses FOR UPDATE on the nullable side
    # of an outer join outright. The lock that matters is this row's; the
    # person-level serialisation belongs to recovery, not to payout.
    locked = PayrollRecord.objects.select_for_update(of=('self',)).select_related(
        'period', 'staff').get(pk=record.pk)

    if locked.status == PayrollRecord.Status.PAID:
        raise PayoutError('This payroll has already been paid.')
    if locked.status != PayrollRecord.Status.APPROVED:
        raise PayoutError(
            'Only approved payroll can be paid. Approve the week first.')
    if locked.net_payable is None:
        raise PayoutError(
            'This payroll has no payable figure -- it cannot have been approved '
            'in this state. Generate and approve it again.')

    now = timezone.now()
    # A savepoint around the insert. Catching an IntegrityError inside an
    # atomic block without one leaves the connection in an aborted state, so
    # the clean "already paid" answer below would be followed by a 500 on the
    # very next query -- and in a test, by "current transaction is aborted".
    # superadmin/audit.py contains its own writes the same way.
    try:
        with transaction.atomic():
            payout = Payout.objects.create(
                payroll_record=locked,
                staff=locked.staff,
                staff_name_snapshot=locked.staff_name_snapshot,
                amount=locked.net_payable,
                method=method,
                reference=str(reference or '').strip()[:120],
                note=str(note or '').strip()[:255],
                paid_at=now,
                paid_by=user,
            )
    except IntegrityError:
        raise PayoutError('This payroll has already been paid.')

    locked.status = PayrollRecord.Status.PAID
    locked.paid_at = now
    locked.save(update_fields=['status', 'paid_at'])
    return payout
