from django.db import migrations, models


def backfill(apps, schema_editor):
    # Runs once per tenant schema (migrate_schemas), so the count restarts at
    # #1 for every boutique. Oldest order first, id as the tie-break.
    Order = apps.get_model('crm_api', 'Order')
    for number, order in enumerate(
            Order.objects.filter(order_number__isnull=True).order_by('order_date', 'id'), 1):
        order.order_number = number
        order.save(update_fields=['order_number'])


class Migration(migrations.Migration):

    dependencies = [
        ('crm_api', '0036_rename_pressing_to_packaging'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='order_number',
            field=models.PositiveIntegerField(blank=True, db_index=True, null=True, unique=True),
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
