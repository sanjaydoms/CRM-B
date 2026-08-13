from django.db import migrations, models


class Migration(migrations.Migration):
    """ErrorEvent.boutique names only the latest occurrence; this is the list.

    Existing rows get [] rather than [boutique]: the field's promise is "every
    boutique this bug has been seen in", and for a row recorded before this
    migration that set is not knowable -- only its last member is. Backfilling
    the last one would make [] mean "one boutique" and dress a guess up as a
    record. It fills in from the next occurrence.
    """

    dependencies = [
        ('superadmin', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='errorevent',
            name='boutiques',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
