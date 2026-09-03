"""Give weeks approved before Phase 6 a payable figure, so they can be paid.

`net_payable` arrived nullable and empty. A week approved under Phase 4 or 5
therefore has a gross and (from Phase 5) a net-after-deposit, but no
net_payable -- and record_payout refuses a null, while generate refuses to touch
an approved week. Without this, every payroll approved before the upgrade is a
dead end: owed, locked, and unpayable.

The figure is what those weeks actually meant: gross less deposit (Phase 5), or
plain gross (Phase 4, which had no deposit column). No advance existed then, so
no advance is subtracted. Idempotent: only rows still null are touched.
"""

from django.db import migrations
from django.db.models import F


def backfill(apps, schema_editor):
    PayrollRecord = apps.get_model('payroll', 'PayrollRecord')
    rows = PayrollRecord.objects.filter(
        net_payable__isnull=True, gross_earnings__isnull=False)
    rows.filter(net_before_other_deductions__isnull=False).update(
        net_payable=F('net_before_other_deductions'))
    rows.filter(net_before_other_deductions__isnull=True).update(
        net_payable=F('gross_earnings'))


class Migration(migrations.Migration):

    dependencies = [
        ('payroll', '0005_one_cancel_per_advance'),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
