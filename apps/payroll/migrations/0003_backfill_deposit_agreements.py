"""Give deposits agreed before the ledger existed a row to stand on.

Phases 1 to 4 let an owner set `StaffProfile.deposit_total` with nowhere for it
to be recorded. From Phase 5 the obligation is derived from the ledger, so any
boutique that had already agreed a deposit would show an agreed amount of zero
and recover nothing from it -- the terms would be on the profile and invisible
to payroll.

One agreement row per profile that already carries a deposit, dated at migration
time. It is not the real date the terms were agreed, and it does not pretend to
be: `note` says exactly where the figure came from, so nobody reading the ledger
later mistakes it for a decision somebody made that day.

Idempotent by construction -- it writes only where no agreement row exists, so
re-running it (or running it on a schema cloned from an already-migrated
template) adds nothing.
"""

from django.db import migrations


def backfill(apps, schema_editor):
    StaffProfile = apps.get_model('staff', 'StaffProfile')
    StaffLedgerEntry = apps.get_model('payroll', 'StaffLedgerEntry')

    already = set(
        StaffLedgerEntry.objects.filter(entry_type='DEPOSIT_AGREED')
        .values_list('staff_id', flat=True))

    for profile in StaffProfile.objects.select_related('staff').all():
        if profile.staff_id is None or profile.staff_id in already:
            continue
        if not profile.deposit_total or profile.deposit_total <= 0:
            continue
        StaffLedgerEntry.objects.create(
            staff_id=profile.staff_id,
            staff_name_snapshot=profile.staff.name,
            entry_type='DEPOSIT_AGREED',
            amount=profile.deposit_total,
            balance_before=0,
            balance_after=profile.deposit_total,
            note='Opening balance from employment terms',
        )


def unbackfill(apps, schema_editor):
    """Remove only what this migration could have written.

    Keyed on the note, because a recovery or a later agreement made after the
    backfill is real history and must survive a reverse.
    """
    StaffLedgerEntry = apps.get_model('payroll', 'StaffLedgerEntry')
    StaffLedgerEntry.objects.filter(
        entry_type='DEPOSIT_AGREED',
        note='Opening balance from employment terms').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('payroll', '0002_staffledgerentry_and_deposit_snapshot'),
        ('staff', '0002_attendancesession'),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
