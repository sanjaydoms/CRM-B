# Generated to safely backfill any missing columns on existing tenant databases
# without breaking fresh test database creations.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('alterations', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            ALTER TABLE alterations_alterationrequest ADD COLUMN IF NOT EXISTS inspection_notes text DEFAULT '';
            ALTER TABLE alterations_alterationrequest ADD COLUMN IF NOT EXISTS inspection_adjustments jsonb DEFAULT '{}';
            ALTER TABLE alterations_alterationrequest ADD COLUMN IF NOT EXISTS notes text DEFAULT '';
            ALTER TABLE alterations_alterationrequest ADD COLUMN IF NOT EXISTS cancelled_at timestamp with time zone NULL;

            ALTER TABLE alterations_alterationactivity ADD COLUMN IF NOT EXISTS performed_by_name varchar(150) DEFAULT '';
            ALTER TABLE alterations_alterationactivity ADD COLUMN IF NOT EXISTS from_status varchar(50) DEFAULT '';
            ALTER TABLE alterations_alterationactivity ADD COLUMN IF NOT EXISTS to_status varchar(50) DEFAULT '';

            ALTER TABLE alterations_alterationpayment ADD COLUMN IF NOT EXISTS received_by_name varchar(150) DEFAULT '';

            ALTER TABLE alterations_alterationmaterialline ADD COLUMN IF NOT EXISTS recorded_by_name varchar(150) DEFAULT '';
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
