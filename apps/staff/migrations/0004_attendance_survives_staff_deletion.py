"""Attendance survives the roster row it belonged to.

`AttendanceSession.staff` was CASCADE, so deleting a staff member deleted every
shift they had worked -- including the shifts an approved and PAID payslip was
computed from. PayrollRecord is SET_NULL with its own snapshots and survived;
the hours behind it did not. The boutique kept the payment and lost the reason
for it.

Two additive columns and one relaxed foreign key. Nothing is dropped, nothing is
rewritten, and no row is deleted.

THE BACKFILL ONLY COPIES WHAT IS THERE
Every existing session still has its `staff` row -- CASCADE guaranteed that, and
it is the reason there is anything to copy. So the snapshot is taken from the
live relationship and nothing is invented: a session whose staff row is somehow
already missing (a hand-edited database) is left with empty strings rather than
a guessed name, and `staff_label` answers "Former staff member" for it.

Idempotent by construction: it writes only where the snapshot is still empty, so
re-running it, or running it against a schema cloned from an already-migrated
template, changes nothing.
"""

import django.db.models.deletion
from django.db import migrations, models


def freeze_identity(apps, schema_editor):
    AttendanceSession = apps.get_model('staff', 'AttendanceSession')
    rows = (AttendanceSession.objects
            .select_related('staff')
            .filter(staff__isnull=False, staff_name_snapshot=''))
    for session in rows.iterator(chunk_size=500):
        session.staff_name_snapshot = session.staff.name
        session.staff_role_snapshot = session.staff.role or ''
        session.save(update_fields=['staff_name_snapshot', 'staff_role_snapshot'])


def unfreeze(apps, schema_editor):
    """Reverse leaves the columns in place for RemoveField to drop.

    Deliberately a no-op rather than a blanking pass: unapplying this migration
    removes the columns anyway, and a bulk UPDATE over historical rows on the
    way out is a destructive operation for no benefit.
    """


class Migration(migrations.Migration):

    dependencies = [
        ('crm_api', '0028_order_discount'),
        ('staff', '0003_performance_review'),
    ]

    operations = [
        migrations.AddField(
            model_name='attendancesession',
            name='staff_name_snapshot',
            field=models.CharField(blank=True, default='', max_length=150),
        ),
        migrations.AddField(
            model_name='attendancesession',
            name='staff_role_snapshot',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
        migrations.AlterField(
            model_name='attendancesession',
            name='staff',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='attendance_sessions', to='crm_api.tailor'),
        ),
        migrations.RunPython(freeze_identity, unfreeze),
    ]
